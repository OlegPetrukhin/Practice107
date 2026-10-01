const text = document.getElementById('text');
const send = document.getElementById('send');
const message = document.getElementById('message');
const result = document.getElementById('result');
const taskId = document.getElementById('taskId');
const status = document.getElementById('status');
const output = document.getElementById('output');

function showMessage(value, type = '') {
  message.textContent = value;
  message.className = `message ${type}`;
}

async function poll(id) {
  const response = await fetch(`/api/tasks/${id}`);
  const data = await response.json();

  if (!response.ok) {
    throw new Error(data.error || 'Не удалось получить статус задачи');
  }

  status.textContent = data.status;

  if (data.status === 'completed') {
    output.textContent = JSON.stringify(data.result, null, 2);
    showMessage('Обработка завершена.', 'success');
    return;
  }

  if (data.status === 'failed') {
    output.textContent = data.error || 'Worker вернул ошибку';
    showMessage('Задача завершилась с ошибкой.', 'error');
    return;
  }

  setTimeout(() => poll(id).catch(err => showMessage(err.message, 'error')), 1000);
}

send.addEventListener('click', async () => {
  const value = text.value.trim();
  if (!value) {
    showMessage('Введите текст.', 'error');
    return;
  }

  send.disabled = true;
  showMessage('Создание задачи...');
  result.classList.remove('hidden');
  output.textContent = '';

  try {
    const response = await fetch('/api/tasks', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({text: value})
    });
    const data = await response.json();

    if (!response.ok) {
      throw new Error(data.error || 'Ошибка Backend');
    }

    taskId.textContent = data.task_id;
    status.textContent = data.status;
    showMessage('Задача поставлена в очередь.', 'success');
    await poll(data.task_id);
  } catch (error) {
    showMessage(error.message, 'error');
  } finally {
    send.disabled = false;
  }
});
