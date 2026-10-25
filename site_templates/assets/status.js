(() => {
  const brief = document.getElementById("current-brief");
  const notice = document.getElementById("freshness-notice");
  function expire() {
    if (brief && Date.now() >= Date.parse(brief.dataset.expires)) {
      brief.hidden = true;
      notice.textContent = "장전 자료의 유효 기한이 지났습니다. 현재 유효한 장전 연구가 없습니다.";
    }
  }
  expire();
  setInterval(expire, 60000);
})();
