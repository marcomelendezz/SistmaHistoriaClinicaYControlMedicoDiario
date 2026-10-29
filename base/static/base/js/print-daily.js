document.getElementById('print-daily-pdf')?.addEventListener('click', () => {
    const frame = document.getElementById('daily-pdf');
    document.getElementById('print-daily-help').textContent = 'Si tu navegador no abre el diálogo, utiliza el botón de impresión del visor o abre el PDF en otra pestaña.';
    try {
        frame.contentWindow.focus();
        frame.contentWindow.print();
    } catch (_) {
        // The native PDF viewer can isolate its print API; the toolbar remains available.
    }
});
