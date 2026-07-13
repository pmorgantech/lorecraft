//! `proxy.rs` — transparent HTTP reverse proxy to the Python backend.
//!
//! Phase 3b, Option A: the Rust gateway is the single front door. It terminates
//! `/ws` itself (see [`crate::ws_player`]) and answers `/healthz` locally; every
//! **other** request is forwarded verbatim to the Python uvicorn origin
//! ([`crate::gateway::GatewayConfig::backend_url`]) by [`proxy_handler`], wired as
//! the router's `.fallback(...)` so those two local routes keep precedence.
//!
//! The passthrough is deliberately *transparent*: method, path, query, headers
//! (minus hop-by-hop) and the full body go upstream unchanged, and the upstream
//! status, headers (minus hop-by-hop) and body come back unchanged. Redirects are
//! **not** followed (a `303` from `/lobby/create` must reach the browser so *it*
//! follows it), and `Set-Cookie` (`lorecraft_session`) is relayed untouched so the
//! browser binds the session to the Rust origin and replays it on later requests.
//!
//! # Buffering limitation
//! Both request and response bodies are fully buffered ([`reqwest::Response::bytes`]).
//! That is correct and sufficient for the 3b player flow (lobby/login HTML, static
//! assets, `POST /auth/ws-ticket`, `POST /command` HTMX partials — all finite
//! payloads). It is **not** suitable for Server-Sent Events / open-ended streaming
//! responses, which would never finish buffering. The player UI uses none (its live
//! channel is the terminated WebSocket, not SSE); admin streaming, if any, is 3c's
//! concern.

use axum::body::Body;
use axum::extract::{Request, State};
use axum::http::{HeaderMap, HeaderName, StatusCode};
use axum::response::{IntoResponse, Response};

use crate::gateway::GatewayState;

/// Upper bound on a buffered request/response body (64 MiB). Generous enough for
/// static assets served through the proxy while still bounding memory per request;
/// an over-limit request is answered `413` rather than allowed to exhaust memory.
const MAX_BODY_BYTES: usize = 64 * 1024 * 1024;

/// Build the shared reverse-proxy HTTP client.
///
/// Redirect following is disabled so upstream 3xx responses pass through to the
/// browser unchanged, and OS/env proxies are ignored — the backend is a fixed
/// loopback origin, so an ambient `HTTP_PROXY` must not silently reroute traffic.
///
/// The builder is infallible in this configuration (no TLS backend to initialize,
/// no custom resolver), so the `expect` documents a genuine invariant rather than
/// guarding a reachable failure.
pub(crate) fn build_http_client() -> reqwest::Client {
    reqwest::Client::builder()
        .redirect(reqwest::redirect::Policy::none())
        .no_proxy()
        .build()
        .expect("reqwest client with no TLS/proxy/custom-resolver is infallible")
}

/// True for RFC 7230 §6.1 hop-by-hop headers (plus the `Proxy-*` family), which a
/// proxy must consume rather than forward. `HeaderName` compares case-insensitively
/// and is stored lowercased, so the string checks below are exact.
fn is_hop_by_hop(name: &HeaderName) -> bool {
    const HOP_BY_HOP: [&str; 7] = [
        "connection",
        "keep-alive",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "proxy-authenticate",
    ];
    let n = name.as_str();
    HOP_BY_HOP.contains(&n) || n.starts_with("proxy-")
}

/// Copy request headers destined for the upstream, dropping hop-by-hop headers and
/// the `Host`/`Content-Length` pair — the HTTP client sets those from the upstream
/// URL and the (re-buffered) body, so forwarding the inbound values would mislabel
/// the request to a backend that may reject a mismatched `Host`.
fn upstream_request_headers(src: &HeaderMap) -> HeaderMap {
    let mut out = HeaderMap::with_capacity(src.len());
    for (name, value) in src {
        if is_hop_by_hop(name) || name == "host" || name == "content-length" {
            continue;
        }
        out.append(name.clone(), value.clone());
    }
    out
}

/// Copy upstream response headers back to the client, dropping only hop-by-hop
/// headers. Everything else — `Set-Cookie`, `Location`, `Content-Type`, cache
/// headers — is relayed verbatim so the session cookie and redirect target survive.
fn downstream_response_headers(src: &HeaderMap) -> HeaderMap {
    let mut out = HeaderMap::with_capacity(src.len());
    for (name, value) in src {
        if is_hop_by_hop(name) {
            continue;
        }
        out.append(name.clone(), value.clone());
    }
    out
}

/// Router `.fallback(...)` handler: forward any request not matched by a local
/// route (`/ws`, `/admin/ws`, `/healthz`) to the Python backend and relay the
/// response transparently. `Request` is the final extractor because it consumes
/// the body; `State` (a `FromRequestParts` extractor) precedes it.
pub(crate) async fn proxy_handler(State(state): State<GatewayState>, req: Request) -> Response {
    let (parts, body) = req.into_parts();

    let body_bytes = match axum::body::to_bytes(body, MAX_BODY_BYTES).await {
        Ok(bytes) => bytes,
        Err(err) => {
            tracing::warn!(error = %err, "rejecting oversized/broken request body");
            return (StatusCode::PAYLOAD_TOO_LARGE, "request body too large").into_response();
        }
    };

    // Origin-form target: path + optional query, appended to the configured base.
    let path_and_query = parts
        .uri
        .path_and_query()
        .map_or(parts.uri.path(), |pq| pq.as_str());
    let base = state.config.backend_url.trim_end_matches('/');
    let upstream_url = format!("{base}{path_and_query}");

    let upstream = state
        .http_client
        .request(parts.method.clone(), &upstream_url)
        .headers(upstream_request_headers(&parts.headers))
        .body(body_bytes)
        .send()
        .await;

    match upstream {
        Ok(resp) => relay_response(resp).await,
        Err(err) => {
            tracing::warn!(
                error = %err,
                url = %upstream_url,
                method = %parts.method,
                "upstream request to python backend failed"
            );
            (StatusCode::BAD_GATEWAY, "upstream backend unavailable").into_response()
        }
    }
}

/// Buffer the upstream response and rebuild it as an axum response, preserving
/// status and (non-hop-by-hop) headers while never following the redirect itself.
async fn relay_response(resp: reqwest::Response) -> Response {
    let status = resp.status();
    let headers = downstream_response_headers(resp.headers());
    let bytes = match resp.bytes().await {
        Ok(bytes) => bytes,
        Err(err) => {
            tracing::warn!(error = %err, "reading upstream response body failed");
            return (StatusCode::BAD_GATEWAY, "upstream response read failed").into_response();
        }
    };
    let mut out = Response::new(Body::from(bytes));
    *out.status_mut() = status;
    *out.headers_mut() = headers;
    out
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::header::{
        CONNECTION, CONTENT_LENGTH, CONTENT_TYPE, HOST, LOCATION, SET_COOKIE, TRANSFER_ENCODING,
        UPGRADE,
    };
    use axum::http::HeaderValue;

    #[test]
    fn hop_by_hop_classification() {
        assert!(is_hop_by_hop(&CONNECTION));
        assert!(is_hop_by_hop(&TRANSFER_ENCODING));
        assert!(is_hop_by_hop(&UPGRADE));
        assert!(is_hop_by_hop(&HeaderName::from_static("keep-alive")));
        assert!(is_hop_by_hop(&HeaderName::from_static("te")));
        assert!(is_hop_by_hop(&HeaderName::from_static("trailer")));
        assert!(is_hop_by_hop(&HeaderName::from_static(
            "proxy-authorization"
        )));
        assert!(is_hop_by_hop(&HeaderName::from_static(
            "proxy-authenticate"
        )));

        assert!(!is_hop_by_hop(&CONTENT_TYPE));
        assert!(!is_hop_by_hop(&SET_COOKIE));
        assert!(!is_hop_by_hop(&LOCATION));
    }

    #[test]
    fn request_headers_drop_hop_by_hop_host_and_length() {
        let mut src = HeaderMap::new();
        src.insert(HOST, HeaderValue::from_static("gateway.example"));
        src.insert(CONTENT_LENGTH, HeaderValue::from_static("123"));
        src.insert(CONNECTION, HeaderValue::from_static("keep-alive"));
        src.insert(CONTENT_TYPE, HeaderValue::from_static("application/json"));
        src.insert("cookie", HeaderValue::from_static("lorecraft_session=abc"));

        let out = upstream_request_headers(&src);

        assert!(!out.contains_key(HOST), "client sets Host from the URL");
        assert!(
            !out.contains_key(CONTENT_LENGTH),
            "client sets Content-Length"
        );
        assert!(!out.contains_key(CONNECTION), "hop-by-hop dropped");
        assert_eq!(out.get(CONTENT_TYPE).unwrap(), "application/json");
        assert_eq!(out.get("cookie").unwrap(), "lorecraft_session=abc");
    }

    #[test]
    fn response_headers_keep_set_cookie_and_location_drop_hop_by_hop() {
        let mut src = HeaderMap::new();
        src.insert(
            SET_COOKIE,
            HeaderValue::from_static("lorecraft_session=abc; Path=/; HttpOnly"),
        );
        src.insert(LOCATION, HeaderValue::from_static("/lobby/created"));
        src.insert(TRANSFER_ENCODING, HeaderValue::from_static("chunked"));
        src.insert(CONNECTION, HeaderValue::from_static("close"));

        let out = downstream_response_headers(&src);

        assert_eq!(
            out.get(SET_COOKIE).unwrap(),
            "lorecraft_session=abc; Path=/; HttpOnly",
            "session cookie must pass through untouched"
        );
        assert_eq!(out.get(LOCATION).unwrap(), "/lobby/created");
        assert!(!out.contains_key(TRANSFER_ENCODING));
        assert!(!out.contains_key(CONNECTION));
    }

    #[test]
    fn response_headers_preserve_multiple_set_cookie_values() {
        let mut src = HeaderMap::new();
        src.append(SET_COOKIE, HeaderValue::from_static("a=1"));
        src.append(SET_COOKIE, HeaderValue::from_static("b=2"));

        let out = downstream_response_headers(&src);

        let cookies: Vec<_> = out.get_all(SET_COOKIE).iter().collect();
        assert_eq!(cookies.len(), 2, "both Set-Cookie values survive");
    }
}
