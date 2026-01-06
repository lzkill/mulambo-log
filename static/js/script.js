document.addEventListener('DOMContentLoaded', () => {
    const startBtn = document.getElementById('start-btn');
    const settingsForm = document.getElementById('settings-form');
    const imageSourceSelection = document.getElementById('image-source-selection');
    const cameraOptions = document.getElementById('camera-options');
    const cameraContainer = document.getElementById('camera-container');
    const video = document.getElementById('video');
    const snapBtn = document.getElementById('snap');
    const switchCameraBtn = document.getElementById('switch-camera');
    const canvas = document.getElementById('canvas');
    const loading = document.getElementById('loading');
    const btnCamera = document.getElementById('btn-camera');
    const btnUpload = document.getElementById('btn-upload');
    const btnFrontCam = document.getElementById('btn-front-cam');
    const btnBackCam = document.getElementById('btn-back-cam');
    const startCameraBtn = document.getElementById('start-camera-btn');
    const fileInput = document.getElementById('file-input');

    const now = new Date();
    
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
    let currentFacingMode = 'user';
    let selectedSize = 'small';
    let selectedPosition = 'top-left';
    
    const sizePresets = {
        'small': { width: 250, height: 166, dpi: 80 },
        'medium': { width: 400, height: 266, dpi: 100 },
        'large': { width: 550, height: 366, dpi: 120 }
    };
    
    document.querySelectorAll('.option-card[data-size]').forEach(card => {
        card.addEventListener('click', () => {
            document.querySelectorAll('.option-card[data-size]').forEach(c => c.classList.remove('active'));
            card.classList.add('active');
            selectedSize = card.dataset.size;
        });
    });
    
    document.querySelectorAll('.pos-btn[data-position]').forEach(btn => {
        addClickEvent(btn, () => {
            document.querySelectorAll('.pos-btn[data-position]').forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            selectedPosition = btn.dataset.position;
        });
    });
    
    function calculatePosition(position, imageWidth, imageHeight, graphWidth, graphHeight) {
        const margin = 20;
        let x, y;
        
        switch(position) {
            case 'top-left':
                x = margin;
                y = margin;
                break;
            case 'top-right':
                x = imageWidth - graphWidth - margin;
                y = margin;
                break;
            case 'center':
                x = (imageWidth - graphWidth) / 2;
                y = (imageHeight - graphHeight) / 2;
                break;
            case 'bottom-left':
                x = margin;
                y = imageHeight - graphHeight - margin;
                break;
            case 'bottom-right':
                x = imageWidth - graphWidth - margin;
                y = imageHeight - graphHeight - margin;
                break;
            default:
                x = margin;
                y = margin;
        }
        
        return { x: Math.max(0, x), y: Math.max(0, y) };
    }

    startBtn.addEventListener('click', async () => {
        startBtn.disabled = true;
        startBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Registrando...';
        
        try {
            const response = await fetch('/record_workout', { method: 'POST' });
            const data = await response.json();
            
            if (data.status === 'success') {
                settingsForm.style.display = 'none';
                imageSourceSelection.style.display = 'block';
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

    function addClickEvent(element, handler) {
        if (!element) return;
        element.addEventListener('click', handler);
        element.addEventListener('touchend', (e) => {
            e.preventDefault();
            handler(e);
        });
    }

    addClickEvent(btnCamera, () => {
        imageSourceSelection.style.display = 'none';
        cameraOptions.style.display = 'block';
        currentFacingMode = 'user';
        btnFrontCam.classList.add('active');
    });

    addClickEvent(btnFrontCam, () => {
        currentFacingMode = 'user';
        btnFrontCam.classList.add('active');
        btnBackCam.classList.remove('active');
    });

    addClickEvent(btnBackCam, () => {
        currentFacingMode = 'environment';
        btnBackCam.classList.add('active');
        btnFrontCam.classList.remove('active');
    });

    addClickEvent(startCameraBtn, () => {
        accessCamera();
    });

    addClickEvent(btnUpload, () => {
        fileInput.click();
    });

    fileInput.addEventListener('change', (e) => {
        const file = e.target.files[0];
        if (file) {
            const reader = new FileReader();
            reader.onload = (event) => {
                processUploadedImage(event.target.result);
            };
            reader.readAsDataURL(file);
        }
    });

    async function accessCamera() {
        cameraOptions.style.display = 'none';
        cameraContainer.style.display = 'block';
        
        try {
            if (stream) {
                stream.getTracks().forEach(track => track.stop());
            }
            
            stream = await navigator.mediaDevices.getUserMedia({ 
                video: { facingMode: currentFacingMode }, 
                audio: false 
            });
            video.srcObject = stream;
        } catch (err) {
            alert('Não foi possível acessar a câmera. Verifique as permissões.');
        }
    }

    switchCameraBtn.addEventListener('click', () => {
        currentFacingMode = currentFacingMode === 'user' ? 'environment' : 'user';
        accessCamera();
    });

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
                }, 200);
            }
        }, 1000);
    }

    async function processUploadedImage(imageDataUrl) {
        imageSourceSelection.style.display = 'none';
        loading.style.display = 'block';
        
        const img = new Image();
        img.onload = () => {
            const context = canvas.getContext('2d');
            canvas.width = img.width;
            canvas.height = img.height;
            context.drawImage(img, 0, 0);
            const imageData = canvas.toDataURL('image/png');
            sendToServer(imageData);
        };
        img.src = imageDataUrl;
    }

    async function captureAndProcess() {
        const context = canvas.getContext('2d');
        canvas.width = video.videoWidth;
        canvas.height = video.videoHeight;
        context.drawImage(video, 0, 0, canvas.width, canvas.height);
        
        const imageData = canvas.toDataURL('image/png');
        
        if (stream) {
            stream.getTracks().forEach(track => track.stop());
        }
        
        cameraContainer.style.display = 'none';
        loading.style.display = 'block';
        
        sendToServer(imageData);
    }

    async function sendToServer(imageData) {
        const sizePreset = sizePresets[selectedSize];
        
        const img = new Image();
        img.onload = async () => {
            const position = calculatePosition(
                selectedPosition, 
                img.width, 
                img.height, 
                sizePreset.width, 
                sizePreset.height
            );
            
            const params = {
                width: sizePreset.width,
                height: sizePreset.height,
                x: position.x,
                y: position.y,
                start_date: document.getElementById('start_date').value,
                end_date: document.getElementById('end_date').value
            };

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
        };
        img.src = imageData;
    }
});
