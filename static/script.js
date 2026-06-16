async function validarFactura() {
    const claveInput = document.getElementById('claveAcceso');
    const claveAcceso = claveInput.value.trim();
    const ambiente = document.getElementById('ambiente').value;
    const resultDiv = document.getElementById('result');
    const loaderDiv = document.getElementById('loader');
    const btnValidar = document.getElementById('btnValidar');

    // Limpiar resultado anterior
    resultDiv.style.display = 'none';
    resultDiv.className = '';
    resultDiv.innerHTML = '';

    if (claveAcceso.length !== 49) {
        mostrarResultado(false, "La clave de acceso debe tener exactamente 49 dígitos numéricos.");
        return;
    }

    // Mostrar loading
    loaderDiv.style.display = 'block';
    btnValidar.disabled = true;

    try {
        const response = await fetch('/api/validar', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ clave_acceso: claveAcceso, ambiente: ambiente })
        });

        const data = await response.json();

        if (response.ok && !data.error) {
            if (data.valida) {
                let html = `<div class="result-item"><span class="result-label">Estado:</span> ${data.estado} ✅</div>`;
                if (data.fecha_autorizacion) {
                    html += `<div class="result-item"><span class="result-label">Fecha:</span> ${data.fecha_autorizacion}</div>`;
                }
                if (data.ambiente) {
                    html += `<div class="result-item"><span class="result-label">Ambiente:</span> ${data.ambiente}</div>`;
                }
                mostrarResultado(true, html, true);
            } else {
                let msg = data.mensaje || "Factura no válida o rechazada.";
                mostrarResultado(false, `<span class="result-label">Estado:</span> ${data.estado || 'RECHAZADO'} ❌<br><br>${msg}`, true);
            }
        } else {
            mostrarResultado(false, data.error || "Ocurrió un error al procesar la solicitud.");
        }
    } catch (error) {
        console.error('Error:', error);
        mostrarResultado(false, "No se pudo conectar con el servidor. Verifica que esté en ejecución.");
    } finally {
        // Ocultar loading
        loaderDiv.style.display = 'none';
        btnValidar.disabled = false;
    }
}

function mostrarResultado(esExito, mensajeHTML, isHTML = false) {
    const resultDiv = document.getElementById('result');
    resultDiv.style.display = 'block';
    resultDiv.className = esExito ? 'success' : 'error';
    if (isHTML) {
        resultDiv.innerHTML = mensajeHTML;
    } else {
        resultDiv.textContent = mensajeHTML;
    }
}

// Permitir enviar con Enter
document.getElementById('claveAcceso').addEventListener('keypress', function (e) {
    if (e.key === 'Enter') {
        validarFactura();
    }
});