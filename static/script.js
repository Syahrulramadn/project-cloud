document.addEventListener('DOMContentLoaded', function() {
    const flashContainer = document.querySelector('.flash-messages-container');
    const flashAlerts = document.querySelectorAll('.flash-alert');

    if (flashContainer && flashAlerts.length > 0) {
      // Tampilkan container dan alert
      setTimeout(() => {
        flashContainer.classList.add('show');
        
        flashAlerts.forEach((alert, index) => {
          setTimeout(() => {
            alert.classList.add('show', 'visible');
          }, index * 200);
        });
      }, 100);

      // Sembunyikan alert
      flashAlerts.forEach(alert => {
        setTimeout(() => {
          alert.classList.remove('show', 'visible');
          
          setTimeout(() => {
            flashContainer.classList.remove('show');
          }, 500);
        }, 5000);
      });
    }
  });