# InterviewOS Deployment Guide

This document covers deployment configurations for InterviewOS infrastructure components.

## GlitchTip Error Tracking

GlitchTip is deployed as a self-hosted error tracking service compatible with Sentry SDK.

### Deployment Location
```
/home/agentops/services/glitchtip/
├── docker-compose.glitchtip.yml   # Main deployment configuration
├── .env.example                    # Environment variable template
├── .env                            # Actual environment variables (not in git)
└── README.md                       # Deployment instructions
```

### Quick Deploy

1. **Navigate to deployment directory:**
   ```bash
   cd /home/agentops/services/glitchtip
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your values (SECRET_KEY, POSTGRES_PASSWORD, etc.)
   ```

3. **Start services:**
   ```bash
   docker-compose -f docker-compose.glitchtip.yml up -d
   ```

4. **Run initial migrations:**
   ```bash
   docker exec -it glitchtip-web ./manage.py migrate
   docker exec -it glitchtip-web ./manage.py createsuperuser
   ```

5. **Access dashboard:**
   ```
   http://your-server-ip:8000
   ```

### Configuration for InterviewOS

After deploying GlitchTip:

1. Create a new project in GlitchTip dashboard
2. Get the DSN from Project Settings
3. Update `backend/.env`:
   ```env
   SENTRY_DSN=https://your-dsn@your-server:8000/project-id
   SENTRY_ENVIRONMENT=production
   SENTRY_TRACES_SAMPLE_RATE=0.1
   ```

### Architecture

The GlitchTip deployment includes:

- **PostgreSQL 15**: Database for error events and user data
- **Redis 7**: Cache and Celery message broker
- **Web Service**: Django application on port 8000
- **Worker Service**: Celery worker for background jobs
- **Beat Service**: Celery beat for scheduled tasks

All services run in isolated Docker containers with health checks and automatic restart policies.

### Monitoring

Check service status:
```bash
cd /home/agentops/services/glitchtip
docker-compose -f docker-compose.glitchtip.yml ps
```

View logs:
```bash
docker-compose -f docker-compose.glitchtip.yml logs -f web
docker-compose -f docker-compose.glitchtip.yml logs -f worker
```

### Backup

Backup database:
```bash
docker exec glitchtip-postgres pg_dump -U glitchtip glitchtip > backup-$(date +%Y%m%d).sql
```

### See Also

- Full deployment documentation: `/home/agentops/services/glitchtip/README.md`
- GlitchTip official docs: https://glitchtip.com/documentation
- Sentry SDK integration: `backend/agents/interview_agent.py`
