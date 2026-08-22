.PHONY: build up down logs migrate makemigrations showmigrations createsuperuser shell test startapp clean \
        tailwind-install tailwind-build tailwatch

# Build or rebuild Docker images
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

# Create new Django migrations
makemigrations:
	docker compose exec web python manage.py makemigrations

# Show the status of all database migrations
showmigrations:
	docker compose exec web python manage.py showmigrations

# Create a Django superuser
createsuperuser:
	docker compose exec web python manage.py createsuperuser

# Open a Django shell inside the running container
shell:
	docker compose exec web python manage.py shell

# Run Django tests
test:
	docker compose exec web python manage.py test

# Scaffold a new Django app
# Usage:
#   make startapp name=properties
startapp:
	docker compose exec web python manage.py startapp $(name)

# Stop containers and remove volumes
# WARNING: This deletes Docker volumes, including your database volume.
clean:
	docker compose down -v


# =============================================================================
# Tailwind CSS
# =============================================================================

# Install Tailwind dependencies
# Requires Node.js and npm on the host machine.
tailwind-install:
	cd theme/static_src && npm install --no-audit --no-fund

# Build Tailwind CSS and collect Django static files
tailwind-build:
	python manage.py tailwind build
	python manage.py collectstatic --noinput

# Run Tailwind in watch/development mode
# Run this in a separate terminal alongside Django.
tailwatch:
	cd theme/static_src && npm run dev