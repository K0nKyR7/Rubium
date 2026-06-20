// Копирование текста
document.querySelectorAll('.copy-btn').forEach(btn => {
    btn.addEventListener('click', async (e) => {
        e.preventDefault();
        const textToCopy = btn.dataset.copy;
        try {
            await navigator.clipboard.writeText(textToCopy);
            const originalText = btn.textContent;
            btn.textContent = '✓ Скопировано!';
            setTimeout(() => {
                btn.textContent = originalText;
            }, 1500);
        } catch (err) {
            console.error('Ошибка копирования:', err);
        }
    });
});

// Маска для телефона
const phoneInput = document.getElementById('phoneInput');
if (phoneInput) {
    IMask(phoneInput, { mask: '+{7} (000) 000-00-00' });
}

// Отправка формы
const form = document.getElementById('contactForm');
const formMessage = document.getElementById('formMessage');
const modal = document.getElementById('successModal');
const modalClose = document.querySelector('.modal-close');

if (form) {
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const submitBtn = form.querySelector('button');
        submitBtn.disabled = true;
        submitBtn.textContent = 'Отправка...';
        
        try {
            const formData = new FormData(form);
            const response = await fetch(form.action, {
                method: 'POST',
                body: formData,
                headers: { 'Accept': 'application/json' }
            });
            
            if (response.ok) {
                form.reset();
                if (phoneInput) phoneInput.value = '';
                modal.classList.add('show');
                setTimeout(() => {
                    modal.classList.remove('show');
                }, 3000);
            } else {
                throw new Error('Ошибка');
            }
        } catch (error) {
            formMessage.className = 'form-message error';
            formMessage.textContent = '❌ Ошибка отправки. Попробуйте позже.';
            setTimeout(() => {
                formMessage.className = 'form-message';
                formMessage.textContent = '';
            }, 3000);
        } finally {
            submitBtn.disabled = false;
            submitBtn.textContent = 'Отправить сообщение';
        }
    });
}

// Закрытие модального окна
if (modalClose) {
    modalClose.addEventListener('click', () => {
        modal.classList.remove('show');
    });
}

// Закрытие модального окна по клику вне его
if (modal) {
    modal.addEventListener('click', (e) => {
        if (e.target === modal) {
            modal.classList.remove('show');
        }
    });
}

// Добавление в закладки
function addToFavorites() {
    const title = document.title;
    const url = window.location.href;
    try {
        if (window.external && 'AddFavorite' in window.external) {
            window.external.AddFavorite(url, title);
        } else {
            alert('Нажмите Ctrl+D (или Cmd+D на Mac), чтобы добавить сайт в закладки.');
        }
    } catch (e) {
        alert('Нажмите Ctrl+D (или Cmd+D на Mac), чтобы добавить сайт в закладки.');
    }
}
window.addToFavorites = addToFavorites;

// Текущий год
document.addEventListener('DOMContentLoaded', () => {
    const yearSpan = document.getElementById('currentYear');
    if (yearSpan) yearSpan.textContent = new Date().getFullYear();
});