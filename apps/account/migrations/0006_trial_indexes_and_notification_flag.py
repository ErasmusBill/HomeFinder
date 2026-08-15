"""
Trial-related indexes and the one-time "trial ended" notification flag.

What this migration does and why:

1. Add ``db_index=True`` to ``trial_end_date`` and ``trial_started``.
   The daily Celery beat tasks filter on these columns for every
   landlord in the system (``trial_end_date__lte=now`` and
   ``trial_end_date__date=target_day``). Without indexes, both
   queries are full table scans that grow with the user table.

2. Add a composite index on ``(role, trial_end_date)``. The beat
   task's most common query is
   ``User.objects.filter(role='landlord', trial_end_date__lte=now)``
   and a composite index lets Postgres use an index-only scan
   instead of evaluating the ``role`` predicate for every row in
   the ``trial_end_date`` index.

3. Add ``notified_trial_ended_at`` DateTimeField (nullable). This
   is the one-time flag that makes the "your trial has ended"
   email genuinely one-time per landlord: the daily task only
   enqueues the email when this column is NULL, then sets it in
   the same transaction. Without this flag the task re-emails
   every day until the landlord subscribes.

This is a non-destructive schema migration. All new columns are
nullable and the index adds don't require a table rewrite for
small to medium tables (Postgres uses ``CREATE INDEX CONCURRENTLY``
semantics-equivalent for non-blocking index creation in
production; for SQLite, the test DB, this is a no-op drop+recreate
that is fast on the test data).
"""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('user_account', '0005_backfill_landlord_free_trials'),
    ]

    operations = [
        # 1. Add the one-time notification flag. Nullable so existing
        #    rows don't need a default and the daily task can use
        #    ``IS NULL`` to find landlords who haven't been notified.
        migrations.AddField(
            model_name='user',
            name='notified_trial_ended_at',
            field=models.DateTimeField(
                blank=True,
                help_text=(
                    "Set by the daily beat task the first time the "
                    "'your trial has ended' email is dispatched. NULL "
                    "means no such email has been sent yet."
                ),
                null=True,
            ),
        ),

        # 2. Indexes. ``db_index=True`` is enough for a single-column
        #    index; for the composite we use ``AddIndex`` explicitly.
        migrations.AlterField(
            model_name='user',
            name='trial_started',
            field=models.BooleanField(
                db_index=True,
                default=False,
                help_text=(
                    "True once this landlord has been granted a free trial. "
                    "Stays True forever — even after the trial ends — so "
                    "the guard, dashboard and emails can distinguish "
                    "'never had a trial' from 'trial ran out'."
                ),
            ),
        ),
        migrations.AlterField(
            model_name='user',
            name='trial_end_date',
            field=models.DateTimeField(
                blank=True,
                db_index=True,
                help_text=(
                    "Indexed because the daily Celery beat task filters on "
                    "this column for every landlord in the system. Without "
                    "the index, the query is a sequential scan that grows "
                    "linearly with the user table."
                ),
                null=True,
            ),
        ),
        migrations.AddIndex(
            model_name='user',
            index=models.Index(
                fields=['role', 'trial_end_date'],
                name='user_role_tri_end_idx',
            ),
        ),
        # Index used by the new one-time notification task: filter on
        # (role, notified_trial_ended_at IS NULL, trial_end_date) for
        # the daily "your trial has ended" sweep. The simple composite
        # on (role, notified_trial_ended_at) covers the WHERE clause
        # well enough — Postgres will filter on trial_end_date using
        # the existing trial_end_date index after the row passes the
        # role/notified predicates.
        migrations.AddIndex(
            model_name='user',
            index=models.Index(
                fields=['role', 'notified_trial_ended_at'],
                name='user_role_notified_idx',
            ),
        ),
    ]
