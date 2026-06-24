/* Lightweight custom tooltips for [data-tip] elements.
   Appended to <body> and position:fixed, so they appear instantly on hover
   and are never clipped by a container's overflow (e.g. tables). */
(function () {
  var tip = null;

  function ensure() {
    if (!tip) {
      tip = document.createElement("div");
      tip.className = "tip-bubble";
      tip.setAttribute("role", "tooltip");
      document.body.appendChild(tip);
    }
    return tip;
  }

  function show(el) {
    var text = el.getAttribute("data-tip");
    if (!text) return;
    var t = ensure();
    t.textContent = text;
    t.style.display = "block";
    t.style.left = "0px";
    t.style.top = "0px";
    var r = el.getBoundingClientRect();
    var tw = t.offsetWidth, th = t.offsetHeight, pad = 8;
    var left = r.left + r.width / 2 - tw / 2;
    left = Math.max(pad, Math.min(left, window.innerWidth - tw - pad));
    var top = r.bottom + pad;
    if (top + th > window.innerHeight - pad) top = r.top - th - pad; // flip above
    t.style.left = left + "px";
    t.style.top = Math.max(pad, top) + "px";
    t.style.opacity = "1";
  }

  function hide() {
    if (tip) { tip.style.opacity = "0"; tip.style.display = "none"; }
  }

  function target(e) {
    return e.target && e.target.closest ? e.target.closest("[data-tip]") : null;
  }

  document.addEventListener("mouseover", function (e) { var el = target(e); if (el) show(el); });
  document.addEventListener("mouseout", function (e) { if (target(e)) hide(); });
  document.addEventListener("focusin", function (e) { var el = target(e); if (el) show(el); });
  document.addEventListener("focusout", hide);
  document.addEventListener("scroll", hide, true);
  window.addEventListener("resize", hide);
})();
