.PHONY: build up down logs migrate showmigrations createsuperuser shell test startapp clean tailwind-install tailwind-build tailwatch

# Build or rebuild docker images
build:
	docker compose build

# Start all containers in the background
up:
	docker compose up -d

# Stop and remove containers
down:
	docker compose down

# View logs from all containers (Ctrl+C to exit)
logs:
	docker compose logs -f

# Run database migrations inside the web container
migrate:
	docker compose exec web python manage.py migrate

# Show the status of all database migrations
showmigrations:
	docker compose exec web python manage.py showmigrations

# Create a new superuser account
createsuperuser:
	docker compose exec web python manage.py createsuperuser

# Open a Django shell inside the running container
shell:
	docker compose exec web python manage.py shell

# Run Django tests
test:
	docker compose exec web python manage.py test

# Scaffold a new Django app (usage: make startapp name=myapp)
startapp:
	docker compose exec web python manage.py startapp $(name)

# Stop containers and remove volumes (Warning: resets database data!)
clean:
	docker compose down -v

# ---------------------------------------------------------------------------
# Tailwind CSS (runs locally — Node/npm must be installed on the host)
# ---------------------------------------------------------------------------
# One-time install of tailwindcss + @tailwindcss/cli into the theme app's
# node_modules directory. Re-run only when upgrading the Tailwind version.
tailwind-install:
	cd theme/static_src && npm install --no-audit --no-fund

# Compile the production CSS into theme/static/css/dist/styles.css
# (re-run this any time you add or change Tailwind class names anywhere
# in the project, or after pulling new template changes).
tailwind-build:
	python manage.py tailwind build
	python manage.py collectstatic --noinput

# Watch-mode build — rebuilds the CSS on every template change. Intended
# for local development. Run alongside `runserver` in another terminal.
tailwatch:
	cd theme/static_src && npm run dev
