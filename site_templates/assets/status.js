(() => {
  const brief = document.getElementById("current-brief");
  const notice = document.getElementById("freshness-notice");
  function expire() {
    if (notice) {
      const date = new Intl.DateTimeFormat("en-CA", {
        timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
      });
      if (date.format(new Date()) !== date.format(new Date(notice.dataset.asOf))) {
        if (brief) brief.hidden = true;
        notice.textContent = "사이트 갱신이 지연됐습니다. 현재 유효한 장전 연구와 거래일 상태를 확인할 수 없습니다.";
        return;
      }
    }
    if (brief && Date.now() >= Date.parse(brief.dataset.expires)) {
      brief.hidden = true;
      notice.textContent = "장전 자료의 유효 기한이 지났습니다. 현재 유효한 장전 연구가 없습니다.";
    }
  }
  expire();
  setInterval(expire, 60000);
})();
