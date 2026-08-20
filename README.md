# VacantHommie

**Author:** ErasmusBill

VacantHommie is a modern rental property platform designed to make it easier for tenants to discover suitable properties and for landlords and agents to manage and publish rental listings.

The project is built around a **Django monolithic architecture**, with a strong emphasis on maintainability, separation of concerns, performance, asynchronous background processing, caching, security, and a user-friendly rental experience.

---

## Table of Contents

- [About VacantHommie](#about-vacanthommie)
- [Project Goals](#project-goals)
- [Core Features](#core-features)
- [Architecture](#architecture)
- [Technology Stack](#technology-stack)
- [Application Structure](#application-structure)
- [Service-Layer Architecture](#service-layer-architecture)
- [Selectors](#selectors)
- [Caching](#caching)
- [Background Task Processing](#background-task-processing)
- [Redis](#redis)
- [Celery and Celery Beat](#celery-and-celery-beat)
- [Database](#database)
- [Authentication and Authorization](#authentication-and-authorization)
- [Property Verification](#property-verification)
- [Media and Image Processing](#media-and-image-processing)
- [Chatbot and AI Architecture](#chatbot-and-ai-architecture)
- [Security](#security)
- [Performance Considerations](#performance-considerations)
- [Deployment](#deployment)
- [Environment Variables](#environment-variables)
- [Development Setup](#development-setup)
- [Project Workflow](#project-workflow)
- [Future Improvements](#future-improvements)
- [Author](#author)

---

# About VacantHommie

VacantHommie is a rental property discovery and management platform focused on simplifying the process of finding and renting properties.

The platform is designed with the realities of the Ghanaian rental market in mind. Tenants can search for properties based on location, price, property type, amenities, bedrooms, furnishing status, and other requirements.

Landlords and agents can create property listings, provide property information and media, manage their listings, and submit properties for verification before publication.

The platform also provides an administrative layer for managing users, properties, verification, locations, amenities, and other platform operations.

VacantHommie is intended to evolve into a complete rental ecosystem where tenants, landlords, agents, and administrators interact through a single platform.

---

# Project Goals

The primary goals of VacantHommie are:

- Make property discovery easier for tenants.
- Help landlords and agents reach potential tenants.
- Improve trust through property verification.
- Provide structured property and location information.
- Make property search fast and efficient.
- Provide a scalable architecture for future growth.
- Reduce unnecessary database queries through caching.
- Move expensive operations into background workers.
- Maintain a clean separation between business logic and HTTP views.
- Provide a foundation for AI-assisted property discovery.
- Support future mobile and third-party integrations.

---

# Core Features

## Tenant Features

Tenants can:

- Create an account.
- Log in and manage their profile.
- Browse available properties.
- Search for properties.
- Filter properties by location.
- Filter properties by price.
- Filter by bedrooms and other property features.
- View detailed property information.
- View property images and media.
- Save properties as favorites.
- View previously viewed properties.
- Request property viewings.
- Manage account settings.
- Interact with the VacantHommie AI assistant.

## Landlord and Agent Features

Landlords and agents can:

- Create accounts.
- Manage their profiles.
- Add property locations.
- Add amenities.
- Create property listings.
- Upload property media.
- Update property information.
- Submit properties for verification.
- Manage published and unpublished listings.
- Monitor property activity.

## Administration Features

Administrators can:

- Manage users.
- Review properties.
- Verify properties.
- Manage property publication status.
- Manage locations.
- Manage amenities.
- Monitor platform activity.
- Manage platform configuration.

---

# Architecture

VacantHommie follows a **Django monolithic architecture**.

The application is intentionally kept as a modular monolith rather than being split into microservices.

This approach allows the project to maintain:

- Simple deployment.
- Centralized authentication.
- Shared database transactions.
- Shared business logic.
- Easier development.
- Lower infrastructure complexity.
- Clear application boundaries.

The architecture can later evolve into separate services if the scale of the platform requires it.

## High-Level Architecture

```text
                         ┌─────────────────────┐
                         │       Browser       │
                         │  Desktop / Mobile  │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │   Django Templates  │
                         │     Tailwind CSS    │
                         │     JavaScript      │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │    Django Views     │
                         │ HTTP / Form Logic   │
                         └──────────┬──────────┘
                                    │
                                    ▼
                         ┌─────────────────────┐
                         │      Services       │
                         │   Business Logic    │
                         └──────────┬──────────┘
                                    │
                         ┌──────────┴──────────┐
                         │                     │
                         ▼                     ▼
                ┌─────────────────┐   ┌─────────────────┐
                │    Selectors    │   │ Background Jobs │
                │ Data Retrieval  │   │     Celery      │
                └────────┬────────┘   └────────┬────────┘
                         │                     │
                         ▼                     ▼
                ┌─────────────────┐   ┌─────────────────┐
                │   PostgreSQL     │   │      Redis      │
                │    Database      │   │ Cache / Broker  │
                └─────────────────┘   └─────────────────┘
```

---

# Technology Stack

## Backend

- Python
- Django
- Django Templates
- Django Forms

## Frontend

- HTML
- Tailwind CSS
- JavaScript

## Database

- PostgreSQL

## Caching

- Redis
- Django Cache Framework

## Background Processing

- Celery
- Celery Beat
- Redis

## Image Processing

- Pillow
- BlurHash

## Deployment

- Railway
- Docker
- Nginx where required by the deployment architecture

## Development Tools

- Git
- GitHub
- Linux
- Python virtual environments
- Environment variables

---

# Application Structure

A simplified application structure looks like this:

```text
vacant_hommie/
│
├── apps/
│   ├── account/
│   ├── tenant/
│   ├── landlord/
│   ├── property/
│   ├── locations/
│   ├── chatbot/
│   └── common/
│
├── config/
│   ├── settings/
│   ├── urls.py
│   ├── celery.py
│   └── wsgi.py
│
├── templates/
│
├── static/
│
├── media/
│
├── manage.py
├── requirements.txt
├── Dockerfile
└── README.md
```

The exact application names can evolve as the project grows, but the architectural principle remains the same: each Django application owns a clearly defined domain.

---

# Service-Layer Architecture

Business logic is separated from HTTP handling through a service layer.

Instead of placing complex business logic directly inside `views.py`, views delegate operations to services.

For example:

```text
Request
   │
   ▼
View
   │
   ▼
Service
   │
   ├── Validation
   ├── Business Rules
   ├── Database Operations
   ├── Cache Invalidation
   └── Background Task Scheduling
```

This provides several advantages:

- Views remain small.
- Business logic can be reused.
- Complex operations are easier to test.
- Background tasks can reuse the same services.
- Database operations are easier to reason about.
- The application becomes easier to maintain.

---

# Selectors

VacantHommie uses selectors to separate data retrieval from business logic.

Selectors are primarily responsible for retrieving data.

Examples include:

```python
get_published_properties()
get_property_by_slug()
get_featured_properties()
get_recent_properties()
get_properties_by_region()
get_properties_by_district()
get_properties_by_area()
get_properties_by_price()
search_properties()
get_property()
```

A selector should focus on retrieving information rather than performing unrelated business operations.

For example:

```text
View
  ↓
Service
  ↓
Selector
  ↓
Database
```

This separation makes database access predictable and reusable.

---

# Caching

Caching is used to reduce unnecessary database queries and improve response times.

VacantHommie uses **Redis as the caching backend** through Django's cache framework.

Frequently accessed or relatively stable data can be cached.

Examples include:

- Published properties.
- Featured properties.
- Recent properties.
- Locations.
- Districts.
- Areas.
- Amenities.
- Frequently requested property information.

A simplified caching flow looks like this:

```text
                 Request
                    │
                    ▼
              Django View
                    │
                    ▼
              Check Redis
                /      \
             HIT        MISS
              │           │
              ▼           ▼
          Return      PostgreSQL
          Cached          │
          Data            ▼
                       Store in
                        Redis
                          │
                          ▼
                       Return
```

## Cache Invalidation

Caching must be combined with proper invalidation.

For example, when a property is updated:

```text
Update Property
      │
      ▼
Database Updated
      │
      ▼
Invalidate Property Cache
      │
      ▼
Invalidate Relevant Listing Caches
```

This prevents users from receiving stale property information.

Cache invalidation is especially important for:

- Property publication status.
- Property verification status.
- Property prices.
- Property availability.
- Property media.
- Featured listings.
- Search result caches.

---

# Background Task Processing

VacantHommie uses background processing for operations that do not need to block the user's HTTP request.

The goal is to keep web requests fast.

Instead of:

```text
User Request
     │
     ▼
Django
     │
     ▼
Expensive Operation
     │
     ▼
Response
```

the system can use:

```text
User Request
     │
     ▼
Django
     │
     ├──────────────► Celery
     │                  │
     ▼                  ▼
Immediate Response   Background Task
                        │
                        ▼
                     Result
```

Examples of suitable background tasks include:

- Sending emails.
- Processing images.
- Generating BlurHash values.
- Cleaning expired records.
- Sending notifications.
- Performing scheduled maintenance.
- Generating reports.
- Processing AI-related workloads.
- Rebuilding search or knowledge indexes.

The request/response cycle should not be blocked by expensive operations when they can safely run asynchronously.

---

# Redis

Redis serves multiple purposes in the architecture.

## 1. Cache

Django uses Redis to store frequently accessed data.

```text
Django
  │
  ▼
Redis
  │
  └── Cached application data
```

## 2. Celery Message Broker

Redis can also act as the message broker between Django/Celery and background workers.

```text
Django
  │
  ▼
Redis
  │
  ▼
Celery Worker
  │
  ▼
Background Task
```

Using Redis for both caching and task brokering keeps the initial infrastructure relatively simple.

As the system grows, dedicated infrastructure can be introduced where appropriate.

---

# Celery and Celery Beat

## Celery

Celery handles asynchronous background jobs.

Example:

```python
send_verification_email.delay(user.id)
```

Instead of making the user wait for the email operation to finish, Django submits the task to Celery and immediately continues.

## Celery Beat

Celery Beat handles scheduled tasks.

Examples:

```text
Every hour
    ↓
Clean expired data

Every day
    ↓
Send reminder notifications

Every night
    ↓
Perform maintenance tasks

Periodically
    ↓
Generate platform reports
```

The architecture is:

```text
                   ┌──────────────┐
                   │    Django    │
                   └──────┬───────┘
                          │
                          ▼
                    ┌───────────┐
                    │   Redis   │
                    └─────┬─────┘
                          │
                  ┌───────┴────────┐
                  │                │
                  ▼                ▼
            Celery Worker     Celery Beat
                  │                │
                  ▼                ▼
             Async Jobs       Scheduled Jobs
```

---

# Database

PostgreSQL is the primary relational database for VacantHommie.

The database stores information such as:

- Users.
- Tenant profiles.
- Landlord profiles.
- Properties.
- Property features.
- Property media.
- Amenities.
- Regions.
- Districts.
- Towns.
- Areas.
- Saved properties.
- Property views.
- Viewing requests.
- Chat conversations.
- Chat messages.

The database design emphasizes relational integrity and clear relationships between domain entities.

---

# Authentication and Authorization

VacantHommie uses Django's authentication system and role-based authorization.

Users can have different roles, such as:

```text
TENANT
LANDLORD
ADMIN
```

Permissions are enforced at the backend level.

For example:

```text
Tenant
 ├── Browse properties
 ├── Save properties
 └── Request viewings

Landlord
 ├── Manage properties
 ├── Upload media
 └── Submit properties for verification

Admin
 ├── Verify properties
 ├── Manage users
 └── Manage platform resources
```

Authorization should never depend solely on frontend controls.

The backend always performs the final permission check.

---

# Property Verification

Property verification is a core part of the VacantHommie trust model.

A landlord or agent can submit a property, but submission does not automatically mean that the property becomes publicly available.

The intended workflow is:

```text
Landlord / Agent
       │
       ▼
Create Property
       │
       ▼
Upload Property Information
       │
       ▼
Submit for Verification
       │
       ▼
Admin Review
       │
   ┌───┴────┐
   │        │
Approved   Rejected
   │        │
   ▼        ▼
Published  Changes Required
```

This helps reduce fraudulent, incomplete, or misleading property listings.

---

# Media and Image Processing

Property listings can contain multiple media files.

Image processing can include:

- Image validation.
- Image resizing.
- Thumbnail generation.
- BlurHash generation.
- Media optimization.

BlurHash can provide a lightweight visual placeholder while the full image loads.

Conceptually:

```text
Upload Image
     │
     ▼
Validate
     │
     ▼
Process Image
     │
     ├── Resize / Optimize
     └── Generate BlurHash
     │
     ▼
Store Media
```

Expensive image processing can be moved to Celery as the platform scales.

---

# Chatbot and AI Architecture

VacantHommie is designed to support an AI rental assistant.

The chatbot should not act as an independent source of truth.

Instead:

```text
                       User
                         │
                         ▼
                   Chatbot UI
                         │
                         ▼
                   Django View
                         │
                         ▼
                  AI Service Layer
                         │
                ┌────────┴────────┐
                │                 │
                ▼                 ▼
          AI Model/API       Django Tools
                                  │
                    ┌─────────────┼─────────────┐
                    ▼             ▼             ▼
               Properties     Locations      User Data
                    │             │             │
                    └─────────────┼─────────────┘
                                  ▼
                              PostgreSQL
```

The AI can assist with:

- Natural-language property searches.
- Property recommendations.
- Location discovery.
- Rental FAQs.
- Property explanations.
- Viewing-request assistance.
- Tenant guidance.
- Landlord guidance.

For example:

```text
User:
"Find me a furnished 2-bedroom apartment in East Legon
under GH₵3,000."

        ↓

AI extracts search requirements

        ↓

Django property search tool

        ↓

PostgreSQL

        ↓

Matching properties

        ↓

AI formats the results

        ↓

User receives property cards
```

The AI should never invent property information.

Property prices, availability, locations, verification status, and other dynamic information must come from VacantHommie's backend.

---

# Security

Security is treated as a backend responsibility.

Important practices include:

- Never exposing secret keys to the frontend.
- Keeping environment variables outside source control.
- Validating all form submissions.
- Enforcing authentication on protected views.
- Enforcing role-based permissions.
- Using Django's CSRF protection.
- Validating uploaded media.
- Preventing unauthorized property modification.
- Restricting admin functionality.
- Avoiding direct trust of client-provided user IDs.
- Protecting background task endpoints.
- Applying appropriate database constraints.

The AI layer must also respect Django authorization.

For example, an AI assistant should never be able to bypass:

```python
request.user
```

or Django permission checks.

---

# Performance Considerations

Performance is handled at several levels.

## Database

Use:

- Appropriate indexes.
- `select_related()`.
- `prefetch_related()`.
- Efficient queryset filtering.
- Pagination.
- Proper database constraints.

## Application

Use:

- Service-layer architecture.
- Selectors.
- Caching.
- Lazy evaluation where appropriate.
- Background processing.

## Infrastructure

Use:

- Redis.
- Celery workers.
- PostgreSQL.
- Containerized deployment where appropriate.

The objective is to avoid unnecessary work during a normal HTTP request.

---

# Deployment

VacantHommie is designed to be deployable on platforms such as Railway.

A production architecture can look like:

```text
                         Internet
                            │
                            ▼
                     Railway Platform
                            │
             ┌──────────────┼──────────────┐
             │              │              │
             ▼              ▼              ▼
          Django         Celery          Celery
          Web App        Worker           Beat
             │              │              │
             └──────────────┼──────────────┘
                            │
                    ┌───────┴───────┐
                    │               │
                    ▼               ▼
                PostgreSQL        Redis
```

Docker can be used to create consistent environments between development and production.

---

# Environment Variables

Sensitive configuration should be stored in environment variables.

Example:

```env
SECRET_KEY=your-secret-key
DEBUG=False

DATABASE_URL=your-database-url

REDIS_URL=your-redis-url

OPENAI_API_KEY=your-openai-api-key
```

Environment files containing secrets should never be committed to Git.

Use `.env.example` to document required configuration without exposing actual credentials.

---

# Development Setup

Clone the repository:

```bash
git clone <repository-url>
cd vacant_hommie
```

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it on Linux/macOS:

```bash
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Configure environment variables:

```bash
cp .env.example .env
```

Run migrations:

```bash
python manage.py migrate
```

Create a superuser:

```bash
python manage.py createsuperuser
```

Run the development server:

```bash
python manage.py runserver
```

---

# Running Celery

Start a Celery worker:

```bash
celery -A config worker -l info
```

Start Celery Beat:

```bash
celery -A config beat -l info
```

Depending on the project configuration, both services can be managed independently in production.

---

# Project Workflow

A typical property workflow is:

```text
                    USER
                      │
          ┌───────────┴───────────┐
          │                       │
       Tenant                  Landlord
          │                       │
          ▼                       ▼
     Search Property        Create Property
          │                       │
          ▼                       ▼
     View Property          Add Location
          │                       │
          ▼                       ▼
      Save Property          Add Amenities
          │                       │
          ▼                       ▼
    Request Viewing        Upload Media
                                  │
                                  ▼
                           Submit Verification
                                  │
                                  ▼
                              ADMIN
                                  │
                                  ▼
                              Verify
                                  │
                           ┌──────┴──────┐
                           │             │
                        Approved      Rejected
                           │
                           ▼
                       Published
                           │
                           ▼
                         Tenant
```

---

# Architectural Principles

VacantHommie follows several core architectural principles.

## Separation of Concerns

Views handle HTTP requests.

Services handle business logic.

Selectors handle data retrieval.

Tasks handle asynchronous work.

Models represent domain data.

Templates handle presentation.

## Single Responsibility

Each component should have a clear responsibility.

## Backend as the Source of Truth

Important decisions and authorization checks happen on the backend.

## Performance by Design

Frequently accessed data can be cached, while expensive operations can be moved to background workers.

## Scalability

The project starts as a modular monolith but is structured so individual domains can be extracted into separate services in the future if required.

---

# Future Improvements

Potential future improvements include:

- Advanced property recommendation engine.
- AI-powered rental assistant.
- Semantic property search.
- Property similarity recommendations.
- Improved fraud detection.
- Automated property verification assistance.
- Push notifications.
- Email notification system.
- SMS notifications.
- Mobile application.
- Advanced analytics.
- Search indexing.
- Dedicated search infrastructure.
- Object storage for property media.
- CDN integration.
- Monitoring and observability.
- Rate limiting.
- Automated testing pipelines.
- CI/CD.
- Advanced AI agent workflows.

---

# Long-Term Vision

VacantHommie aims to become more than a property listing website.

The long-term vision is to build a complete rental ecosystem that connects:

```text
                ┌───────────────┐
                │    Tenants    │
                └───────┬───────┘
                        │
                        ▼
               ┌─────────────────┐
               │   VacantHommie  │
               │                 │
               │ Property Search │
               │ Verification    │
               │ Messaging       │
               │ AI Assistant    │
               │ Viewings        │
               │ Notifications   │
               └────────┬────────┘
                        │
              ┌─────────┴─────────┐
              ▼                   ▼
       ┌──────────────┐    ┌──────────────┐
       │  Landlords   │    │    Agents    │
       └──────────────┘    └──────────────┘
```

The goal is to make property discovery safer, faster, and more convenient while providing landlords and agents with reliable tools for managing their rental listings.

---

# Author

**ErasmusBill**

Backend Software Developer and creator of VacantHommie.

---

## License

This project is proprietary unless otherwise stated by the project owner.

© 2026 ErasmusBill. All rights reserved.
