document.addEventListener('DOMContentLoaded', () => {
    const startBtn = document.getElementById('start-btn');
    const settingsForm = document.getElementById('settings-form');
    const cameraContainer = document.getElementById('camera-container');
    const video = document.getElementById('video');
    const snapBtn = document.getElementById('snap');
    const canvas = document.getElementById('canvas');
    const loading = document.getElementById('loading');

    // Set default dates
    const now = new Date();
    
    // Helper to format local date as YYYY-MM-DD
    const formatDate = (date) => {
        const y = date.getFullYear();
        const m = String(date.getMonth() + 1).padStart(2, '0');
        const d = String(date.getDate()).padStart(2, '0');
        return `${y}-${m}-${d}`;
    };

    const firstDay = new Date(now.getFullYear(), 0, 1);
    const lastDay = new Date(now.getFullYear(), 11, 31);
    
    document.getElementById('start_date').value = formatDate(firstDay);
    document.getElementById('end_date').value = formatDate(lastDay);

    let stream = null;

    startBtn.addEventListener('click', async () => {
        // 1. Persist Workout
        startBtn.disabled = true;
        startBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Registrando...';
        
        try {
            const response = await fetch('/record_workout', { method: 'POST' });
            const data = await response.json();
            
            if (data.status === 'success') {
                // 2. Access Native Camera
                accessCamera();
            } else {
                alert('Erro ao registrar treino: ' + data.message);
                startBtn.disabled = false;
                startBtn.innerHTML = '<i class="fas fa-camera"></i> Iniciar Registro';
            }
        } catch (e) {
            alert('Erro de conexão: ' + e);
            startBtn.disabled = false;
        }
    });

    async function accessCamera() {
        settingsForm.style.display = 'none';
        cameraContainer.style.display = 'block';
        
        try {
            stream = await navigator.mediaDevices.getUserMedia({ 
                video: { facingMode: "user" }, 
                audio: false 
            });
            video.srcObject = stream;
        } catch (err) {
            console.error(err);
            alert('Não foi possível acessar a câmera. Verifique as permissões.');
        }
    }

    snapBtn.addEventListener('click', () => {
        const timerVal = parseInt(document.getElementById('timer_val').value) || 0;
        
        if (timerVal > 0) {
            startCountdown(timerVal);
        } else {
            captureAndProcess();
        }
    });

    function startCountdown(seconds) {
        snapBtn.disabled = true;
        let count = seconds;
        snapBtn.innerHTML = `<i class="fas fa-clock"></i> FOTO EM ${count}...`;
        
        const interval = setInterval(() => {
            count--;
            if (count > 0) {
                snapBtn.innerHTML = `<i class="fas fa-clock"></i> FOTO EM ${count}...`;
            } else {
                clearInterval(interval);
                snapBtn.innerHTML = '<i class="fas fa-smile"></i> SORRIA!';
                setTimeout(() => {
                   captureAndProcess(); 
                }, 200); // Small delay for "SORRIA"
            }
        }, 1000);
    }

    async function captureAndProcess() {
        // Capture Photo
        const context = canvas.getContext('2d');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        
        const imageData = canvas.toDataURL('image/png');
        
        // Stop Camera
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
        }
        
        cameraContainer.style.display = 'none';
        loading.style.display = 'block';

        // Collect Params
        const params = {
            width: document.getElementById('g_width').value,
            height: document.getElementById('g_height').value,
            x: document.getElementById('g_x').value,
            y: document.getElementById('g_y').value,
            start_date: document.getElementById('start_date').value,
            end_date: document.getElementById('end_date').value
        };

        // Send to Server
        try {
            const response = await fetch('/process_image', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    image: imageData,
                    graph_params: params
                })
            });
            
            const resData = await response.json();
            if (resData.status === 'success') {
                localStorage.setItem('mulambo_result', resData.image);
                window.location.href = '/result';
            } else {
                alert('Erro ao processar imagem: ' + resData.message);
                window.location.reload();
            }
        } catch (e) {
            alert('Erro de conexão: ' + e);
        }
    }
});
