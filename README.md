Мониторинг REST API

Учебный проект. Два экземпляра приложения, Prometheus, Grafana, генератор дашборда и фоновая нагрузка. Данные хранятся в памяти каждого экземпляра.

## Запуск всего стенда

Нужны Docker с Linux-контейнерами и Docker Compose v2. Для Windows подходит Docker Desktop с WSL 2. Локальные Java, Maven и Python для запуска через Compose не требуются. При первой сборке нужен интернет для скачивания образов и Maven-зависимостей.

Команды выполняются из корня проекта. В Windows PowerShell:

```powershell
Copy-Item .env.example .env
docker compose up
```

В Linux/macOS:

```bash
cp .env.example .env
docker compose up
```

Compose собирает образ приложения при первом запуске. После изменения Java-кода используйте `docker compose up --build`. Для запуска в фоне добавьте `-d`.

После готовности сервисов генератор автоматически публикует дашборд, затем запускается нагрузка. Ожидается, что графики появятся в течение 2–3 минут после готовности стека; первоначальное скачивание и сборка могут занять дополнительное время. Приложение, запущенное из IntelliJ на порту 8080, нужно остановить либо изменить `APP_1_PORT` в `.env`.

| Компонент | Адрес по умолчанию |
|---|---|
| Grafana | [http://localhost:3000](http://localhost:3000) |
| Дашборд | [Items Golden signals](http://localhost:3000/d/items-golden-signals) |
| Prometheus | [http://localhost:9090](http://localhost:9090) |
| Scrape targets | [http://localhost:9090/targets](http://localhost:9090/targets) |
| Готовность первого экземпляра | [http://localhost:8080/health](http://localhost:8080/health) |
| Готовность второго экземпляра | [http://localhost:8081/health](http://localhost:8081/health) |
| Каталог ручек | [http://localhost:8080/handlers](http://localhost:8080/handlers) |
| Метрики первого экземпляра | [http://localhost:8080/metrics](http://localhost:8080/metrics) |
| Метрики второго экземпляра | [http://localhost:8081/metrics](http://localhost:8081/metrics) |

В Grafana войдите с `GRAFANA_ADMIN_USER` и `GRAFANA_ADMIN_PASSWORD` из вашего `.env`. При изменении портов соответственно изменятся адреса в таблице. Опубликованные порты привязаны к `127.0.0.1`.
