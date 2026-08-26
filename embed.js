/* CXO Movement Tracker — embeddable widget.
 * Usage on any website:
 *   <script src="https://USER.github.io/REPO/embed.js"
 *           data-sector="pharma"      (all | bfsi | pharma | healthcare | education | corporate)
 *           data-role="ceo"           (ceo | md | cfo | coo | cmo | chro | cto | cio |
 *                                      cdo | ciso | csuite | chairman | board | head |
 *                                      president — omit for all roles)
 *           data-limit="10"
 *           data-region="India"       (India | Global | omit for both)
 *           data-theme="auto"         (light | dark | auto)
 *           data-title="Pharma leadership moves"></script>
 */
(function () {
  var s = document.currentScript;
  if (!s) return;
  var base = s.src.replace(/embed\.js.*$/, "");
  var sector = (s.getAttribute("data-sector") || "all").toLowerCase();
  var role = (s.getAttribute("data-role") || "").toLowerCase();
  var limit = parseInt(s.getAttribute("data-limit") || "10", 10);
  var region = s.getAttribute("data-region") || "";
  var theme = s.getAttribute("data-theme") || "auto";
  var title = s.getAttribute("data-title") || "Leadership movements";
  if (["all", "bfsi", "pharma", "healthcare", "education", "corporate"].indexOf(sector) < 0) sector = "all";
  // role slug -> role_group label; dedicated role endpoints exist for corporate
  // only. Other sectors filter their _latest feed client-side, so a rare role
  // may return fewer than data-limit rows (the feed holds the 50 newest moves).
  var ROLES = { ceo: "CEO", md: "MD", cfo: "CFO", coo: "COO", cmo: "CMO", chro: "CHRO",
    cto: "CTO", cio: "CIO", cdo: "CDO", ciso: "CISO", csuite: "Other C-suite",
    chairman: "Chairman", academic: "Academic Leadership", board: "Board & Directors",
    head: "Business Heads", president: "President", other: "Other" };
  if (!ROLES[role]) role = "";
  var feed = (role && sector === "corporate") ? "corporate_" + role : sector;

  var host = document.createElement("div");
  s.parentNode.insertBefore(host, s);
  var root = host.attachShadow ? host.attachShadow({ mode: "open" }) : host;

  var css =
    ":host{all:initial}" +
    ".w{font-family:system-ui,-apple-system,'Segoe UI',sans-serif;border:1px solid var(--ring);" +
    "border-radius:12px;background:var(--bg);color:var(--ink);max-width:100%;overflow:hidden}" +
    ".w{--bg:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--ring:rgba(11,11,11,.12);" +
    "--line:#e1e0d9;--up:#006300;--down:#d03b3b;--chip:#f0efec;--link:#2a78d6}" +
    ".w.dark{--bg:#1a1a19;--ink:#fff;--ink2:#c3c2b7;--muted:#898781;--ring:rgba(255,255,255,.12);" +
    "--line:#2c2c2a;--up:#0ca30c;--down:#e66767;--chip:#262624;--link:#3987e5}" +
    ".h{padding:12px 16px;border-bottom:1px solid var(--line);font-weight:700;font-size:15px}" +
    ".h small{display:block;font-weight:400;color:var(--muted);font-size:11px;margin-top:2px}" +
    "ul{list-style:none;margin:0;padding:0}" +
    "li{padding:10px 16px;border-bottom:1px solid var(--line);font-size:13px;line-height:1.45}" +
    "li:last-child{border-bottom:none}" +
    ".p{font-weight:600}.c{color:var(--ink2)}" +
    ".b{display:inline-block;font-size:11px;font-weight:600;padding:1px 8px;border-radius:999px;" +
    "background:var(--chip);margin-right:6px;white-space:nowrap}" +
    ".b.up{color:var(--up)}.b.down{color:var(--down)}.b.flat{color:var(--ink2)}" +
    ".d{color:var(--muted);font-size:11px;margin-left:6px;white-space:nowrap}" +
    "a{color:var(--link);text-decoration:none}a:hover{text-decoration:underline}" +
    ".f{padding:8px 16px;font-size:11px;color:var(--muted);border-top:1px solid var(--line)}" +
    ".f a{color:var(--muted)}";

  var badge = { Appointment: ["▲", "up"], Promotion: ["▲", "up"], "Re-appointment": ["↻", "flat"], Resignation: ["▼", "down"], Retirement: ["▼", "flat"] };

  function esc(t) {
    return String(t == null ? "" : t).replace(/[&<>"]/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c];
    });
  }

  var dark = theme === "dark" || (theme === "auto" && window.matchMedia &&
    window.matchMedia("(prefers-color-scheme: dark)").matches);

  fetch(base + "api/v1/" + feed + "_latest.json")
    .then(function (r) { if (!r.ok) throw new Error(r.status); return r.json(); })
    .then(function (d) {
      var rows = d.records;
      if (role && feed === sector) rows = rows.filter(function (r) { return r.role_group === ROLES[role]; });
      if (region) rows = rows.filter(function (r) { return r.region === region; });
      rows = rows.slice(0, limit);
      var items = rows.map(function (r) {
        var b = badge[r.movement] || ["•", "flat"];
        var head = '<span class="p">' + esc(r.person) + "</span>";
        return "<li><span class='b " + b[1] + "'>" + b[0] + " " + esc(r.movement) + "</span>" +
          head + " — " + esc(r.role) +
          (r.company ? '<span class="c">, ' + esc(r.company) + "</span>" : "") +
          (r.moved_from ? '<span class="c"> (from ' + esc(r.moved_from) + ")</span>" : "") +
          '<span class="d">' + esc(r.date || "") + "</span></li>";
      }).join("");
      root.innerHTML = "<style>" + css + "</style>" +
        '<div class="w' + (dark ? " dark" : "") + '"><div class="h">' + esc(title) +
        "<small>" + esc(d.sector) + (role ? " · " + esc(ROLES[role]) : "") + " · updated " + esc((d.updated || "").slice(0, 10)) + "</small></div>" +
        "<ul>" + (items || "<li class='c'>No records</li>") + "</ul>" +
        '<div class="f">Powered by <a href="' + base + '" target="_blank" rel="noopener">CXO Movement Tracker</a></div></div>';
    })
    .catch(function (e) {
      root.innerHTML = "<style>" + css + "</style>" +
        '<div class="w"><div class="f">CXO widget failed to load (' + esc(e.message) + ")</div></div>";
    });
})();
