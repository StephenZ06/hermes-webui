"""Serve graphify project artifacts under /graphify-projects/*."""

from pathlib import Path


# Graphify pages are local generated artifacts, embedded only by the WebUI's
# same-origin workspace iframe. They need vis-network from its pinned CDN;
# applying the app-wide frame-ancestors 'none' policy would report an intended
# embedding as a violation.
_GRAPHIFY_CSP = (
    "default-src 'self'; object-src 'none'; frame-ancestors 'self'; "
    "script-src 'self' 'unsafe-inline' https://unpkg.com; "
    "worker-src blob: 'self'; style-src 'self' 'unsafe-inline'; "
    "img-src 'self' data: blob:; font-src 'self' data:; "
    "connect-src 'self' https://unpkg.com; base-uri 'none'; form-action 'none'"
)
_GRAPHIFY_CSP_REPORT_ONLY = _GRAPHIFY_CSP + "; report-uri /api/csp-report; report-to csp-endpoint"


def _graphify_html_bridge(data: bytes) -> bytes:
    """Add host controls without changing Graphify's generated graph data."""
    # Graphify emits large vis-network canvases.  vis-network's optional
    # improved layout cannot position some of those networks and logs a noisy
    # warning before falling back; disable that optional pass at construction.
    data = data.replace(
        b"const network = new vis.Network(container, { nodes: nodesDS, edges: edgesDS }, {",
        b"const network = new vis.Network(container, { nodes: nodesDS, edges: edgesDS }, { layout: { improvedLayout: false },",
    )
    bridge = b'''<style id="hermes-graph-host">
:root{color-scheme:light dark}body,#sidebar,#sidebar input,#sidebar button{font-family:var(--graph-font-ui)!important}body{background:var(--graph-bg)!important;color:var(--graph-text)!important}#graph{min-width:0!important;height:100vh!important}#sidebar{position:relative;background:var(--graph-sidebar)!important;border-color:var(--graph-border)!important;color:var(--graph-text)!important;transition:width .2s cubic-bezier(.22,1,.36,1),opacity .18s ease;max-width:72vw}#sidebar.hermes-graph-collapsed{width:0!important;opacity:0;border:0!important}#search-wrap,#info-panel{border-color:var(--graph-border)!important}#search{background:var(--graph-bg)!important;border-color:var(--graph-border)!important;color:var(--graph-text)!important}#search::placeholder{color:var(--graph-muted)!important}.legend-cb,#select-all-cb{appearance:none!important;-webkit-appearance:none!important;display:grid!important;place-content:center!important;width:14px!important;height:14px!important;border:1.5px solid var(--graph-border)!important;border-radius:3px!important;background:var(--graph-bg)!important}.legend-cb:checked,#select-all-cb:checked,.legend-cb:indeterminate,#select-all-cb:indeterminate{background:var(--graph-accent)!important;border-color:var(--graph-accent)!important}.legend-cb:checked::after,#select-all-cb:checked::after{content:''!important;position:static!important;display:block!important;width:3px!important;height:6px!important;margin-top:-1px!important;border:solid var(--graph-surface)!important;border-width:0 2px 2px 0!important;transform:rotate(45deg)!important}.legend-cb:indeterminate::after,#select-all-cb:indeterminate::after{content:''!important;position:static!important;display:block!important;width:7px!important;height:2px!important;border:0!important;background:var(--graph-surface)!important;transform:none!important}#search-results,.search-item:hover,.legend-item:hover{background:var(--graph-hover)!important;border-color:var(--graph-border)!important}#info-panel h3,#legend-wrap h3,#legend-controls label,#stats{color:var(--graph-muted)!important}.graph-sidebar-toggle,.graph-section-toggle{border:1px solid var(--graph-border);border-radius:7px;background:var(--graph-surface);color:var(--graph-text);cursor:pointer}.graph-sidebar-toggle{position:absolute;left:-29px;top:10px;width:28px;height:28px;z-index:4}.graph-section-toggle{float:right;width:22px;height:22px;line-height:1;padding:0}.graph-section-toggle:focus-visible,.graph-sidebar-toggle:focus-visible{outline:2px solid var(--graph-accent);outline-offset:2px}.hermes-graph-section{transition:max-height .2s cubic-bezier(.22,1,.36,1),opacity .16s ease,padding .2s cubic-bezier(.22,1,.36,1);overflow:hidden}.hermes-graph-section.hermes-graph-section-collapsed{min-height:0!important;max-height:42px!important;opacity:.82;padding-bottom:8px!important}.hermes-graph-section.hermes-graph-section-collapsed>*:not(h3){display:none}@media(max-width:360px){#sidebar{width:220px}}@media(prefers-reduced-motion:reduce){#sidebar,.hermes-graph-section{transition:none}}
</style><script id="hermes-graph-host-script">(function(){function apply(tokens){Object.entries(tokens||{}).forEach(function(entry){document.documentElement.style.setProperty('--graph-'+entry[0],entry[1]);});}try{var initial=new URLSearchParams(location.search).get('hermes_graph_theme');if(initial)apply(JSON.parse(initial));}catch(_){ }function ready(){var sidebar=document.getElementById('sidebar'),graph=document.getElementById('graph');if(!sidebar||!graph)return;var redraw=function(){setTimeout(function(){if(window.network&&window.network.redraw)window.network.redraw();},220)};var button=document.createElement('button');button.className='graph-sidebar-toggle';button.type='button';button.id='graph-sidebar-toggle';button.setAttribute('aria-label','Toggle graph sidebar');button.setAttribute('aria-expanded','true');button.textContent=String.fromCharCode(8249);sidebar.appendChild(button);button.onclick=function(){var closed=sidebar.classList.toggle('hermes-graph-collapsed');button.textContent=String.fromCharCode(closed?8250:8249);button.setAttribute('aria-expanded',String(!closed));redraw();};['info-panel','legend-wrap'].forEach(function(id){var panel=document.getElementById(id),heading=panel&&panel.querySelector('h3');if(!heading)return;panel.classList.add('hermes-graph-section');var toggle=document.createElement('button');toggle.className='graph-section-toggle';toggle.type='button';toggle.setAttribute('aria-label','Collapse '+heading.textContent);toggle.setAttribute('aria-expanded','true');toggle.textContent='\\u2212';heading.appendChild(toggle);toggle.onclick=function(){var closed=panel.classList.toggle('hermes-graph-section-collapsed');toggle.textContent=closed?'+':'\\u2212';toggle.setAttribute('aria-expanded',String(!closed));toggle.setAttribute('aria-label',(closed?'Expand ':'Collapse ')+heading.textContent);redraw();};});new ResizeObserver(redraw).observe(graph);window.addEventListener('message',function(event){if(event.source!==window.parent||!event.data||event.data.type!=='hermes-graph-theme')return;apply(event.data.tokens);redraw();});}if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',ready);else ready();})();</script>'''
    bridge += b'''<style id="hermes-graph-host-polish">html,body{margin:0!important;width:100%!important;height:100%!important;overflow:hidden!important;border:0!important}#graph{border:0!important;outline:0!important}.graph-sidebar-toggle{left:auto!important;right:12px!important;top:12px!important;width:29px!important;height:29px!important;transition:right .2s cubic-bezier(.22,1,.36,1),opacity .18s ease}#search-wrap{padding-right:49px!important}</style><script>document.addEventListener('DOMContentLoaded',function(){var button=document.getElementById('graph-sidebar-toggle');if(button)document.body.appendChild(button);});window.addEventListener('load',function(){requestAnimationFrame(function(){requestAnimationFrame(function(){if(window.parent&&window.parent!==window)window.parent.postMessage({type:'hermes-graph-ready'},'*');});});});</script>'''
    bridge += b'''<style id="hermes-graph-sidebar-motion">#sidebar{--hermes-sidebar-width:280px;flex:0 0 var(--hermes-sidebar-width)!important;width:var(--hermes-sidebar-width)!important;overflow:hidden;transition:flex-basis .36s cubic-bezier(.22,1,.36,1),width .36s cubic-bezier(.22,1,.36,1),opacity .2s ease!important;will-change:flex-basis,width,opacity}#sidebar.hermes-graph-collapsed{flex-basis:0!important;width:0!important;pointer-events:none}@media(max-width:360px){#sidebar{--hermes-sidebar-width:220px}}@media(prefers-reduced-motion:reduce){#sidebar{transition:none!important}}#search{height:31px!important;min-height:31px!important;line-height:15px!important}.graph-sidebar-toggle{width:31px!important;height:31px!important;display:grid!important;place-items:center!important;padding:0!important;line-height:1!important}#search-wrap{padding-right:51px!important}</style>'''
    return data.replace(b"</head>", bridge + b"</head>") if b"</head>" in data.lower() else data + bridge


def graphify_static_fallback(_app, handler, parsed):
    """GET /graphify-projects/<path> -> serve from graphify-out/projects/."""
    prefix = "/graphify-projects/"
    if not parsed.path.startswith(prefix):
        return None

    from api.config import REPO_ROOT

    graphify_root = (Path(REPO_ROOT) / "graphify-out" / "projects").resolve()
    rel = parsed.path[len(prefix):].lstrip("/")
    target = (graphify_root / rel).resolve()
    try:
        target.relative_to(graphify_root)
    except ValueError:
        return _not_found(handler)
    if not target.exists() or not target.is_file():
        return _not_found(handler)

    content_types = {
        ".html": "text/html; charset=utf-8",
        ".htm": "text/html; charset=utf-8",
        ".json": "application/json",
    }
    ct = content_types.get(target.suffix.lower(), "text/plain; charset=utf-8")
    cache_control = "no-store" if target.suffix.lower() in {".html", ".htm"} else "public, max-age=300"
    data = target.read_bytes()
    if target.suffix.lower() in {".html", ".htm"}:
        data = _graphify_html_bridge(data)
    handler.send_response(200)
    handler.send_header("Content-Type", ct)
    handler.send_header("Content-Length", str(len(data)))
    handler.send_header("Cache-Control", cache_control)
    if target.suffix.lower() in {".html", ".htm"}:
        handler._csp_report_only_policy = _GRAPHIFY_CSP_REPORT_ONLY
        handler.send_header("Content-Security-Policy", _GRAPHIFY_CSP)
    handler.end_headers()
    handler.wfile.write(data)
    return True


def _not_found(handler):
    body = b'{"error": "not found"}'
    handler.send_response(404)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
    return True
