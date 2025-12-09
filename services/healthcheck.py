"""
Health check HTTP server.

Provides a simple HTTP endpoint for container orchestration
and monitoring systems to check if the bot is alive.
"""
import asyncio
import logging
from aiohttp import web

logger = logging.getLogger(__name__)


class HealthCheckServer:
    """
    Simple HTTP server for health checks.
    
    Exposes /health and /ready endpoints for Kubernetes,
    Docker, or other orchestration systems.
    """
    
    def __init__(self, host: str = "0.0.0.0", port: int = 8080) -> None:
        """
        Initialize health check server.
        
        Args:
            host: Host to bind to
            port: Port to listen on
        """
        self.host = host
        self.port = port
        self.app = web.Application()
        self.runner: web.AppRunner | None = None
        self._is_ready = False
        
        # Setup routes
        self.app.router.add_get("/health", self._health_handler)
        self.app.router.add_get("/ready", self._ready_handler)
        self.app.router.add_get("/", self._health_handler)
    
    async def _health_handler(self, request: web.Request) -> web.Response:
        """
        Health check endpoint.
        
        Returns 200 if the server is running.
        Used for liveness probes.
        """
        return web.json_response({"status": "healthy"})
    
    async def _ready_handler(self, request: web.Request) -> web.Response:
        """
        Readiness check endpoint.
        
        Returns 200 if the bot is ready to handle requests.
        Used for readiness probes.
        """
        if self._is_ready:
            return web.json_response({"status": "ready"})
        return web.json_response(
            {"status": "not ready"},
            status=503
        )
    
    def set_ready(self, ready: bool = True) -> None:
        """Set the readiness status."""
        self._is_ready = ready
    
    async def start(self) -> None:
        """Start the health check server."""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        
        logger.info(f"Health check server started on {self.host}:{self.port}")
    
    async def stop(self) -> None:
        """Stop the health check server."""
        if self.runner:
            await self.runner.cleanup()
            logger.info("Health check server stopped")


# Global instance
_health_server: HealthCheckServer | None = None


def get_health_server(host: str = "0.0.0.0", port: int = 8080) -> HealthCheckServer:
    """Get or create the global health check server."""
    global _health_server
    if _health_server is None:
        _health_server = HealthCheckServer(host=host, port=port)
    return _health_server


async def start_health_server(host: str = "0.0.0.0", port: int = 8080) -> HealthCheckServer:
    """Start the health check server."""
    server = get_health_server(host, port)
    await server.start()
    return server


async def stop_health_server() -> None:
    """Stop the health check server."""
    global _health_server
    if _health_server:
        await _health_server.stop()
        _health_server = None
