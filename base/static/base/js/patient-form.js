(() => {
  const selector = document.getElementById('id_tipo_paciente');
  if (!selector) return;
  const update = () => {
    document.querySelectorAll('[data-patient-types]').forEach(section => {
      section.hidden = !section.dataset.patientTypes.split(' ').includes(selector.value);
    });
  };
  selector.addEventListener('change', update);
  update();
})();
