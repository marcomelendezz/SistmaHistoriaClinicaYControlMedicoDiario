(() => {
  document.documentElement.classList.add('js');
  const button = document.getElementById('menu-toggle');
  const menu = document.getElementById('main-menu');
  if (button && menu) button.addEventListener('click', () => {
    const open = menu.classList.toggle('is-open');
    button.setAttribute('aria-expanded', String(open));
  });
  document.querySelectorAll('form[data-confirm]').forEach(form => {
    form.addEventListener('submit', event => {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });
})();
