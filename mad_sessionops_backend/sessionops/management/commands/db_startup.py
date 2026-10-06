"""
Startup DB check: migrate and print a readable status summary.
Called from entrypoint.sh before the server starts.
Run locally: just dbcheck
"""

import os
import sys

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

SEP = "-" * 62


def _ok(msg):
    return f"  [OK]   {msg}"


def _fail(msg):
    return f"  [FAIL] {msg}"


class Command(BaseCommand):
    help = "Run migrations, print structured startup summary."

    def handle(self, *args, **options):
        self._print_header()
        self._print_db_info()

        migration_ok = self._run_migrations()

        self._print_footer(migration_ok)

        if not migration_ok:
            sys.exit(1)

    # ── Header ─────────────────────────────────────────────────────────────────

    def _print_header(self):
        env = os.environ.get("ENVIRONMENT", "development").upper()
        self.stdout.write(f"\n{SEP}")
        self.stdout.write(f"  SESSION-OPS -- STARTUP   [{env}]")
        self.stdout.write(f"{SEP}\n")

    # ── DB info ────────────────────────────────────────────────────────────────

    def _print_db_info(self):
        cfg = connection.settings_dict
        # Read active schema from PostgreSQL directly
        try:
            with connection.cursor() as cur:
                cur.execute("SELECT current_database(), current_schema()")
                pg_db, pg_schema = cur.fetchone()
        except Exception:
            pg_db, pg_schema = cfg["NAME"], "unknown"

        self.stdout.write(f"  Database : {pg_db}")
        self.stdout.write(f"  Schema   : {pg_schema}")
        self.stdout.write(f"  Host     : {cfg['HOST']}:{cfg.get('PORT', 5432)}\n")

    # ── Migrations ─────────────────────────────────────────────────────────────

    def _run_migrations(self) -> bool:
        self.stdout.write(f"{SEP}")
        self.stdout.write("  MIGRATIONS")
        self.stdout.write(f"{SEP}")

        try:
            executor = MigrationExecutor(connection)
            plan = executor.migration_plan(executor.loader.graph.leaf_nodes())
            pending_count = len(plan)

            if pending_count:
                self.stdout.write(f"  Pending  : {pending_count}")
                for migration, _ in plan:
                    self.stdout.write(f"    -> {migration.app_label}.{migration.name}")
                self.stdout.write("  Applying...")
                call_command(
                    "migrate", "--noinput", "--database", "migrate", verbosity=0, stdout=self.stdout
                )
                self.stdout.write(_ok(f"Applied {pending_count} migration(s)"))
                # Migrations run as DBADMINUSER, so tables they create are owned by
                # the admin. Hand them back to DBUSER (no-op when already correct).
                call_command("fix_table_ownership", stdout=self.stdout)
            else:
                self.stdout.write(_ok("Up to date -- no pending migrations"))

            # Count applied migrations from the loader's applied set
            executor.loader.build_graph()
            applied = len(executor.loader.applied_migrations)
            self.stdout.write(f"  Total applied : {applied}\n")
            return True

        except Exception as exc:
            self.stdout.write(_fail(f"Migration error: {exc}"))
            return False

    # ── Footer ─────────────────────────────────────────────────────────────────

    def _print_footer(self, all_ok: bool):
        self.stdout.write(f"{SEP}")
        if all_ok:
            self.stdout.write("  [OK] DB ready -- starting server")
        else:
            self.stdout.write("  [FAIL] Startup checks failed -- aborting")
        self.stdout.write(f"{SEP}\n")
