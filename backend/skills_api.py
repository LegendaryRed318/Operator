#!/usr/bin/env python3
"""
skills_api.py - HTTP API for skill management, analytics, and dashboard.
Runs on port 8766 alongside the WebSocket server.
"""

import json
import logging
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from pathlib import Path
from typing import Any, Dict

from paths import LOGS_PATH

logger = logging.getLogger(__name__)


class SkillsAPIHandler(BaseHTTPRequestHandler):
    """HTTP request handler for skills API."""

    def _send_json(self, data: Any, status: int = 200):
        """Send JSON response."""
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    def _send_error(self, message: str, status: int = 400):
        """Send error response."""
        self._send_json({"error": message}, status)

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        """Handle GET requests."""
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)

        try:
            if path == '/skills':
                self._handle_list_skills()

            elif path == '/skills/dashboard':
                self._handle_dashboard(query.get('range', ['7d'])[0])

            elif path == '/skills/analytics':
                self._handle_analytics(query.get('range', ['7d'])[0])

            elif path == '/skills/schedules':
                self._handle_list_schedules()

            elif path == '/skills/chains':
                self._handle_list_chains()

            elif path == '/skills/context':
                self._handle_context()

            elif path == '/skills/learned':
                self._handle_learned_triggers()

            elif path == '/health':
                self._send_json({"status": "healthy", "service": "skills-api"})

            elif path == '/health/detailed':
                self._handle_detailed_health()

            else:
                self._send_error("Not found", 404)

        except Exception as e:
            logger.error(f"[SkillsAPI] GET error: {e}")
            self._send_error(str(e), 500)

    def do_POST(self):
        """Handle POST requests."""
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = json.loads(self.rfile.read(content_length).decode()) if content_length > 0 else {}

            if path.startswith('/skills/') and path.endswith('/toggle'):
                skill_name = path.split('/')[2]
                self._handle_toggle_skill(skill_name, body)

            elif path == '/skills/create':
                self._handle_create_skill(body)

            elif path == '/skills/schedule':
                self._handle_create_schedule(body)

            elif path == '/skills/chain/execute':
                self._handle_execute_chain(body)

            elif path == '/skills/learn':
                self._handle_learn_trigger(body)

            elif path == '/skills/export':
                self._handle_export_skill(body)

            elif path == '/skills/import':
                self._handle_import_skill(body)

            else:
                self._send_error("Not found", 404)

        except json.JSONDecodeError:
            self._send_error("Invalid JSON", 400)
        except Exception as e:
            logger.error(f"[SkillsAPI] POST error: {e}")
            self._send_error(str(e), 500)

    def _handle_list_skills(self):
        """List all skills."""
        try:
            from skills import list_skills_snapshot, get_skill_executor

            snapshot = list_skills_snapshot()

            # Add analytics data
            try:
                from skill_analytics import get_skill_stats
                stats = get_skill_stats()

                if isinstance(stats, list):
                    stats_map = {s['skill_name']: s for s in stats}
                else:
                    stats_map = stats

                # Enrich loaded skills with stats
                for skill in snapshot.get('loaded', []):
                    skill_stats = stats_map.get(skill['name'], {})
                    skill['executions'] = skill_stats.get('total_executions', 0)
                    if skill_stats.get('total_executions', 0) > 0:
                        skill['success_rate'] = (
                            skill_stats.get('successful_executions', 0) /
                            skill_stats.get('total_executions', 1) * 100
                        )

            except ImportError:
                pass

            self._send_json(snapshot)

        except Exception as e:
            self._send_error(str(e))

    def _handle_dashboard(self, time_range: str):
        """Get dashboard data."""
        try:
            from skill_analytics import get_dashboard_data
            data = get_dashboard_data()
            self._send_json(data)
        except ImportError:
            self._send_json({"error": "Analytics not available"})

    def _handle_analytics(self, time_range: str = '7d'):
        """Get detailed analytics."""
        try:
            from skill_analytics import (
                get_skill_stats, get_usage_trends, get_top_skills,
                get_recent_executions, get_failure_analysis
            )

            days = int(time_range.replace('d', '')) if time_range else 7

            self._send_json({
                "stats": get_skill_stats(),
                "trends": get_usage_trends(days),
                "top_skills": get_top_skills(10, days),
                "recent": get_recent_executions(20),
                "failures": get_failure_analysis(days),
            })
        except ImportError:
            self._send_json({"error": "Analytics not available"})

    def _handle_toggle_skill(self, skill_name: str, body: Dict[str, Any]):
        """Toggle a skill's enabled state."""
        try:
            enabled = body.get('enabled', True)

            # Update skill file
            skill_file = SKILLS_PATH / f"{skill_name}.toml"

            if skill_file.exists():
                import re

                with open(skill_file, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Replace enabled value
                content = re.sub(
                    r'enabled = (true|false)',
                    f'enabled = {"true" if enabled else "false"}',
                    content
                )

                with open(skill_file, 'w', encoding='utf-8') as f:
                    f.write(content)

                # Reload skills
                try:
                    from skills import reload_skills_cache
                    reload_skills_cache()
                except ImportError:
                    pass

                self._send_json({"success": True, "skill": skill_name, "enabled": enabled})
            else:
                # Built-in skill - can't toggle
                self._send_error(f"Cannot toggle built-in skill: {skill_name}")

        except Exception as e:
            self._send_error(str(e))

    def _handle_create_skill(self, body: Dict[str, Any]):
        """Create a skill from natural language."""
        try:
            user_request = body.get('request', '')

            if not user_request:
                self._send_error("Missing 'request' field")
                return

            from skill_creator import create_skill_from_language
            result = create_skill_from_language(user_request)

            if result.get('success'):
                self._send_json(result, 201)
            else:
                self._send_error(result.get('error', 'Failed to create skill'))

        except Exception as e:
            self._send_error(str(e))

    def _handle_list_schedules(self):
        """List scheduled skills."""
        try:
            from skill_scheduler import get_scheduler

            scheduler = get_scheduler()
            schedules = scheduler.list_schedules()

            self._send_json({"schedules": schedules})
        except Exception as e:
            self._send_error(str(e))

    def _handle_create_schedule(self, body: Dict[str, Any]):
        """Create a skill schedule."""
        try:
            from skill_scheduler import get_scheduler

            scheduler = get_scheduler()
            result = scheduler.add_schedule(
                schedule_id=body.get('id', body.get('skill_name')),
                skill_name=body.get('skill_name'),
                cron_expression=body.get('cron', '0 * * * *'),
                description=body.get('description', ''),
                params=body.get('params', {}),
            )

            if result:
                self._send_json({"success": True})
            else:
                self._send_error("Failed to create schedule")

        except Exception as e:
            self._send_error(str(e))

    def _handle_list_chains(self):
        """List skill chains."""
        try:
            from skill_chaining import get_chain_executor

            executor = get_chain_executor()
            chains = executor.list_chains()

            self._send_json({"chains": chains})
        except Exception as e:
            self._send_error(str(e))

    def _handle_execute_chain(self, body: Dict[str, Any]):
        """Execute a skill chain."""
        try:
            from skill_chaining import execute_skill_chain

            chain_id = body.get('chain_id')
            if not chain_id:
                self._send_error("Missing 'chain_id' field")
                return

            result = execute_skill_chain(chain_id, body.get('context', {}))
            self._send_json(result)

        except Exception as e:
            self._send_error(str(e))

    def _handle_context(self):
        """Get current context."""
        try:
            from skill_context import get_current_context

            self._send_json({"context": get_current_context()})
        except Exception as e:
            self._send_error(str(e))

    def _handle_learned_triggers(self):
        """Get learned triggers."""
        try:
            from skill_learning import get_learner

            learner = get_learner()
            triggers = learner.get_learned_triggers()

            self._send_json({"learned_triggers": triggers})
        except Exception as e:
            self._send_error(str(e))

    def _handle_learn_trigger(self, body: Dict[str, Any]):
        """Learn a new trigger."""
        try:
            from skill_learning import learn_trigger

            skill_name = body.get('skill_name')
            new_trigger = body.get('trigger')
            confidence = body.get('confidence', 1.0)

            if not skill_name or not new_trigger:
                self._send_error("Missing 'skill_name' or 'trigger'")
                return

            result = learn_trigger(skill_name, new_trigger, confidence)
            self._send_json({"success": result})

        except Exception as e:
            self._send_error(str(e))

    def _handle_export_skill(self, body: Dict[str, Any]):
        """Export a skill for sharing."""
        try:
            from skill_sharing import get_sharer

            sharer = get_sharer()
            skill_name = body.get('skill_name')

            if not skill_name:
                self._send_error("Missing 'skill_name'")
                return

            result = sharer.export_skill(skill_name)
            self._send_json(result)

        except Exception as e:
            self._send_error(str(e))

    def _handle_import_skill(self, body: Dict[str, Any]):
        """Import a skill from a package."""
        try:
            from skill_sharing import get_sharer

            sharer = get_sharer()
            package_path = body.get('package_path')

            if not package_path:
                self._send_error("Missing 'package_path'")
                return

            result = sharer.import_skill(package_path, body.get('overwrite', False))
            self._send_json(result)

        except Exception as e:
            self._send_error(str(e))

    def _handle_detailed_health(self):
        """Return detailed health status for all services."""
        import socket
        import subprocess

        def check_port(host: str, port: int) -> bool:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex((host, port))
                sock.close()
                return result == 0
            except:
                return False

        def check_ollama() -> bool:
            try:
                import urllib.request
                req = urllib.request.Request('http://localhost:11434/api/tags', method='GET')
                req.add_header('Accept', 'application/json')
                with urllib.request.urlopen(req, timeout=2) as response:
                    return response.status == 200
            except:
                return False

        health_data = {
            "status": "healthy",
            "services": {
                "api": True,  # We're responding, so API is up
                "websocket": check_port('localhost', 8765),
                "voice": check_port('localhost', 8766),
                "ollama": check_ollama(),
                "frontend": True,  # Frontend is always 'up' if it's calling us
            },
            "timestamp": datetime.now().isoformat()
        }
        self._send_json(health_data)

    def log_message(self, format, *args):
        """Suppress default logging."""
        logger.debug(f"[SkillsAPI] {args[0]}")


# Import SKILLS_PATH from paths module
try:
    from paths import SKILLS_PATH
except ImportError:
    SKILLS_PATH = LOGS_PATH / "skills"


def run_api_server(host: str = 'localhost', port: int = 8766):
    """Run the skills API server."""
    server = HTTPServer((host, port), SkillsAPIHandler)
    logger.info(f"[SkillsAPI] Starting server on http://{host}:{port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("[SkillsAPI] Shutting down")
        server.shutdown()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_api_server()
