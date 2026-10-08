// One visible official YouTube player, no downloaded or extracted recording.
const videoId = 'LTphVIore3A';
const statusLabel = document.getElementById('status');
const playButton = document.getElementById('play');
const seek = document.getElementById('seek');
const volume = document.getElementById('volume');
let player, ready = false, dragging = false;

function stamp(seconds) {
  const value = Math.max(0, Math.floor(seconds || 0));
  const h = Math.floor(value / 3600), m = Math.floor(value / 60) % 60;
  return (h ? h + ':' + String(m).padStart(2, '0') : m) + ':' + String(value % 60).padStart(2, '0');
}
function pauseMusic() { if (ready) player.pauseVideo(); }
function update() {
  if (!ready) return;
  const duration = player.getDuration() || 0;
  const position = player.getCurrentTime() || 0;
  seek.max = Math.max(1, duration);
  seek.disabled = duration <= 0;
  if (!dragging) seek.value = position;
  document.getElementById('time').textContent = stamp(dragging ? seek.value : position) + ' / ' + (duration ? stamp(duration) : '—');
  // Also reflect adjustments made through the standard YouTube controls.
  const level = player.isMuted() ? 0 : player.getVolume();
  if (document.activeElement !== volume) volume.value = level;
  document.getElementById('volume-value').textContent = volume.value + '%';
}
window.onYouTubeIframeAPIReady = () => {
  player = new YT.Player('player', {
    width: '100%', height: '100%', videoId,
    playerVars: { controls: 1, playsinline: 1, origin: location.origin },
    events: {
      onReady: () => {
        ready = true;
        player.setVolume(Number(volume.value));
        for (const id of ['play', 'back', 'forward']) document.getElementById(id).disabled = false;
        statusLabel.textContent = 'Нажмите «Слушать». Камин может продолжать звучать отдельно.';
        update();
      },
      onStateChange: event => {
        if (document.hidden && event.data === YT.PlayerState.PLAYING) { pauseMusic(); return; }
        playButton.textContent = event.data === YT.PlayerState.PLAYING ? 'Пауза' : 'Слушать';
        if (event.data === YT.PlayerState.ENDED && document.getElementById('repeat').checked && !document.hidden) {
          player.seekTo(0, true); player.playVideo();
        }
        update();
      },
      onError: () => { statusLabel.textContent = 'Ролик недоступен в плеере. Попробуйте ссылку «Открыть на YouTube».'; },
      onAutoplayBlocked: () => { statusLabel.textContent = 'Нажмите кнопку воспроизведения на самом видео.'; },
    },
  });
};
playButton.addEventListener('click', () => {
  if (!ready) return;
  if (player.getPlayerState() === YT.PlayerState.PLAYING) pauseMusic();
  else player.playVideo();
});
function skip(delta) {
  if (ready) player.seekTo(Math.max(0, Math.min(player.getDuration(), player.getCurrentTime() + delta)), true);
}
document.getElementById('back').addEventListener('click', () => skip(-30));
document.getElementById('forward').addEventListener('click', () => skip(30));
seek.addEventListener('input', () => { dragging = true; update(); });
seek.addEventListener('change', () => { if (ready) player.seekTo(Number(seek.value), true); dragging = false; });
seek.addEventListener('blur', () => { dragging = false; });
volume.addEventListener('input', () => {
  document.getElementById('volume-value').textContent = volume.value + '%';
  if (ready) { player.unMute(); player.setVolume(Number(volume.value)); }
});
document.addEventListener('visibilitychange', () => { if (document.hidden) pauseMusic(); });
window.addEventListener('pagehide', pauseMusic);
window.addEventListener('message', event => {
  if (event.origin === location.origin && event.data === 'hearth-pause-music') pauseMusic();
});
setInterval(update, 500);
const script = document.createElement('script');
script.src = 'https://www.youtube.com/iframe_api';
script.onerror = () => { statusLabel.textContent = 'Не удалось подключить YouTube. Проверьте интернет или откройте ролик по ссылке.'; };
document.head.appendChild(script);
setTimeout(() => {
  if (!ready) statusLabel.textContent = 'YouTube загружается дольше обычного. Можно открыть ролик по ссылке выше.';
}, 15000);
