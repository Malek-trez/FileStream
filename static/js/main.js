document.addEventListener('DOMContentLoaded', function() {
    const fileInput = document.getElementById('imgInp');
    const imagePreview = document.getElementById('img-upload');

    function readURL(input) {
        if (input.files && input.files[0]) {
            const reader = new FileReader();
            
            reader.onload = function(e) {
                imagePreview.src = e.target.result;
            }
            
            reader.readAsDataURL(input.files[0]);
        }
    }

    fileInput.addEventListener('change', function() {
        readURL(this);
    });

    // Drag and drop handling
    const container = document.querySelector('.file-input-container');
    
    container.addEventListener('dragover', (e) => {
        e.preventDefault();
        container.style.borderColor = '#2563eb';
    });
    
    container.addEventListener('dragleave', () => {
        container.style.borderColor = '#cbd5e1';
    });
    
    container.addEventListener('drop', (e) => {
        e.preventDefault();
        container.style.borderColor = '#cbd5e1';
        fileInput.files = e.dataTransfer.files;
        readURL(fileInput);
    });
});

// Auto-hide alerts after 5 seconds
document.addEventListener('DOMContentLoaded', () => {
    const alerts = document.querySelectorAll('.alert');
    
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.transform = 'translateX(100%)';
            setTimeout(() => alert.remove(), 300);
        }, 5000);
    });
});