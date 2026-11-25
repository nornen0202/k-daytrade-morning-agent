(() => {
  const brief = document.getElementById("current-brief");
  const notice = document.getElementById("freshness-notice");
  if (!notice) return;
  const date = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
  });
  const asOfMs = Date.parse(notice.dataset.asOf || "");
  const expiresMs = Date.parse(brief?.dataset.expires || "");
  const cutoffMs = Date.parse(`${brief?.dataset.reportDate}T09:00:00+09:00`);
  let timer;
  function refresh() {
    clearTimeout(timer);
    const now = Date.now();
    if (!Number.isFinite(asOfMs)) {
      if (brief) brief.hidden = true;
      notice.textContent = "사이트 갱신 시각을 확인할 수 없습니다. 현재 유효한 장전 연구가 없습니다.";
      return;
    }
    if (now < asOfMs) {
      if (brief) brief.hidden = true;
      notice.textContent = "사이트 갱신 시각을 확인 중입니다. 잠시 후 다시 확인합니다.";
      timer = setTimeout(refresh, Math.min(Math.max(asOfMs - now + 250, 250), 60000));
      return;
    }
    if (date.format(now) !== date.format(asOfMs)) {
      if (brief) brief.hidden = true;
      notice.textContent = "사이트 갱신 시각을 확인할 수 없습니다. 현재 유효한 장전 연구가 없습니다.";
      return;
    }
    if (brief) {
      const remaining = expiresMs - now;
      const valid = expiresMs === cutoffMs && remaining > 0
        && date.format(expiresMs) === date.format(asOfMs);
      brief.hidden = !valid;
      notice.textContent = valid
        ? `현재 유효한 장전 연구: ${brief.dataset.reportDate}. 거래일.`
        : "장전 자료의 유효 기한이 지났습니다. 현재 유효한 장전 연구가 없습니다.";
      timer = setTimeout(refresh, valid ? Math.min(remaining, 60000) : 60000);
    } else {
      timer = setTimeout(refresh, 60000);
    }
  }
  refresh();
  document.addEventListener("visibilitychange", refresh);
  window.addEventListener("pageshow", refresh);
})();
