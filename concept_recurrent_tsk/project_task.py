# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from dateutil.relativedelta import relativedelta
from markupsafe import Markup
from datetime import timedelta
import logging

# Optional: to catch DB unique violations robustly during copy()
import psycopg2
from psycopg2.errorcodes import UNIQUE_VIOLATION

_logger = logging.getLogger(__name__)


class ProjectTask(models.Model):
    _inherit = 'project.task'

    # ---------- Fields ----------
    recurring_task = fields.Boolean(string="Recurring Task")
    is_recurring_template = fields.Boolean(string="Is a Recurring Template", default=False, copy=False)
    repeat_intervals = fields.Integer(string="Repeat Every", default=1)
    repeat_unit = fields.Selection([
        ('day', 'Days'),
        ('week', 'Weeks'),
        ('month', 'Months'),
        ('year', 'Years'),
    ], string="Repeat Unit", default='week')
    recurrence_start_date = fields.Date(string="Start From", default=fields.Date.context_today, tracking=True)

    mon = fields.Boolean(string="Mon")
    tue = fields.Boolean(string="Tue")
    wed = fields.Boolean(string="Wed")
    thu = fields.Boolean(string="Thu")
    fri = fields.Boolean(string="Fri")
    sat = fields.Boolean(string="Sat")
    sun = fields.Boolean(string="Sun")

    repeat_type = fields.Selection([
        ('forever', 'Forever'),
        ('until', 'End Date'),
        ('after', 'Number of Repetitions')
    ], string="Stop After", default='forever', required=True, tracking=True)
    repeat_until = fields.Date(string="End Date", tracking=True)
    repeat_number = fields.Integer(string="Repetitions", default=10, tracking=True)

    next_recurrence_date = fields.Date(string="Next Recurrence Date", copy=False, readonly=True, index=True)
    recurrence_left = fields.Integer(string="Remaining Repetitions", copy=False, readonly=True)
    recurrence_message = fields.Html(string="Recurrence Preview", compute='_compute_recurrence_message')

    generated_task_count = fields.Integer(
        string="Generated Tasks",
        readonly=True,
        default=0,
        copy=False,
        compute='_compute_generated_task_count',
        store=False,
        help="The number of tasks that have been generated from this recurring template."
    )

    recurring_template_id = fields.Many2one(
        'project.task',
        string='Recurring Template',
        copy=False,
        index=True,
        ondelete='set null'
    )
    display_task_id = fields.Integer(string="Task ID", related='id', readonly=True)
    is_parent_id_readonly = fields.Boolean(
        string="Is Parent Task Readonly",
        compute='_compute_is_parent_id_readonly'
    )

    # Occurrence date (idempotency on children)
    occurrence_date = fields.Date(string="Occurrence Date", copy=False, index=True)

    recurrence_status = fields.Selection([
        ('running', 'Running'),
        ('stopped', 'Stopped')
    ], string="Recurrence Status", compute="_compute_recurrence_status", store=False)

    def _post_recurrence_info(self, *, context_label):
        """Post a clear chatter line showing current start/end settings."""
        self.ensure_one()
        parts = []
        parts.append(_("Recurring schedule %s") % context_label)
        if self.recurrence_start_date:
            parts.append(_("Start: %s") % format_date(self.env, self.recurrence_start_date))
        if self.repeat_type == 'until' and self.repeat_until:
            parts.append(_("End: %s") % format_date(self.env, self.repeat_until))
        elif self.repeat_type == 'after':
            parts.append(_("Repetitions: %s") % (self.repeat_number or 0))
        body = " | ".join(parts)
        self.message_post(
            body=body,
            message_type='comment',
            subtype_xmlid='mail.mt_comment',  # valid way to set subtype in modern Odoo
        )

    @api.depends('recurring_task', 'next_recurrence_date')
    def _compute_recurrence_status(self):
        today = fields.Date.context_today(self)
        for task in self:
            # Default to stopped
            task.recurrence_status = 'stopped'

            # Running only if:
            # 1) Record is saved (has ID),
            # 2) Recurrence is enabled,
            # 3) Next recurrence is today or later
            if (
                task.id
                and task.recurring_task
                and task.next_recurrence_date
                and task.next_recurrence_date >= today
            ):
                task.recurrence_status = 'running'





    # DB-level idempotency guard: one child per template+date
    _sql_constraints = [
        (
            'uniq_template_occurrence',
            'unique(recurring_template_id, occurrence_date)',
            'A task for this recurrence already exists.'
        )
    ]

    @api.depends('parent_id')
    def _compute_is_parent_id_readonly(self):
        """Read-only parent_id after first save."""
        for task in self:
            task.is_parent_id_readonly = bool(task.parent_id)

    # ---------- Computed fields / helpers ----------
    @api.depends('recurring_task', 'is_recurring_template')
    def _compute_generated_task_count(self):
        for task in self:
            if task.is_recurring_template:
                task.generated_task_count = self.env['project.task'].sudo().search_count([
                    ('recurring_template_id', '=', task.id)
                ])
            else:
                task.generated_task_count = 0

    def _get_next_occurrence_date(self, last_date):
        """Compute next occurrence strictly after last_date."""
        self.ensure_one()
        interval = max(1, int(self.repeat_intervals or 1))

        if self.repeat_unit == 'day':
            return last_date + relativedelta(days=interval)
        if self.repeat_unit == 'month':
            return last_date + relativedelta(months=interval)
        if self.repeat_unit == 'year':
            return last_date + relativedelta(years=interval)

        if self.repeat_unit == 'week':
            selected_weekdays = {
                day for day, sel in {
                    0: self.mon, 1: self.tue, 2: self.wed,
                    3: self.thu, 4: self.fri, 5: self.sat, 6: self.sun
                }.items() if sel
            }
            if not selected_weekdays:
                return None

            # Start from the day after last_date
            next_date = last_date + timedelta(days=1)

            # Interval == 1: pick the next selected weekday this or next week
            if interval == 1:
                while next_date.weekday() not in selected_weekdays:
                    next_date += timedelta(days=1)
                return next_date

            # Intervals > 1: jump week-blocks
            start_of_last_week = last_date - timedelta(days=last_date.weekday())
            next_interval_week_start = start_of_last_week + timedelta(weeks=interval)

            temp_date = next_interval_week_start
            # find first selected weekday in that interval week
            while temp_date.weekday() not in selected_weekdays:
                temp_date += timedelta(days=1)
                if temp_date >= next_interval_week_start + timedelta(days=7):
                    break

            if temp_date <= last_date:
                # fallback to next interval
                temp_date = next_interval_week_start + timedelta(weeks=1)
                while temp_date.weekday() not in selected_weekdays:
                    temp_date += timedelta(days=1)

            return temp_date

        return None
    def _get_recurrence_human_readable(self):
        self.ensure_one()
        if not self.recurring_task:
            return ""

        parts = [f"This task is set to recur, starting from <b>{self.recurrence_start_date.strftime('%d-%m-%Y')}</b>."]

        # Repetition
        repetition = f"It repeats every <b>{self.repeat_intervals} {self.repeat_unit}</b>"
        if self.repeat_unit == 'week':
            days = []
            if self.mon: days.append("Mon")
            if self.tue: days.append("Tue")
            if self.wed: days.append("Wed")
            if self.thu: days.append("Thu")
            if self.fri: days.append("Fri")
            if self.sat: days.append("Sat")
            if self.sun: days.append("Sun")
            if days:
                repetition += f" on <b>{', '.join(days)}</b>"
        parts.append(repetition + ".")

        # End condition
        if self.repeat_type == 'forever':
            parts.append("The recurrence will continue indefinitely.")
        elif self.repeat_type == 'until':
            parts.append(f"The recurrence will stop on <b>{self.repeat_until.strftime('%d-%m-%Y')}</b>.")
        elif self.repeat_type == 'after':
            parts.append(f"The recurrence will stop after <b>{self.repeat_number}</b> repetitions.")

        return Markup("<br/>".join(parts))

    def _compute_first_occurrence_date(self):
        """First valid occurrence on or after start_date."""
        self.ensure_one()
        start_date = self.recurrence_start_date
        if not start_date:
            return None

        temp_date = start_date
        if self.repeat_unit == 'week':
            selected_weekdays = {
                day for day, sel in {
                    0: self.mon, 1: self.tue, 2: self.wed,
                    3: self.thu, 4: self.fri, 5: self.sat, 6: self.sun
                }.items() if sel
            }
            if not selected_weekdays:
                return None
            while temp_date.weekday() not in selected_weekdays:
                temp_date += timedelta(days=1)

        return temp_date

    # ---------- Computed html preview ----------
    @api.depends(
        'recurring_task', 'repeat_intervals', 'repeat_unit',
        'next_recurrence_date', 'repeat_type', 'repeat_until',
        'repeat_number', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'
    )
    def _compute_recurrence_message(self):
        for task in self:
            if not task.recurring_task or not task.next_recurrence_date:
                task.recurrence_message = False
                continue

            dates = [task.next_recurrence_date]
            temp_date = task.next_recurrence_date
            limit = 100 if task.repeat_type != 'after' else (task.repeat_number or 0)

            while len(dates) < limit:
                next_date = task._get_next_occurrence_date(temp_date)
                if not next_date or (task.repeat_type == 'until' and task.repeat_until and next_date > task.repeat_until):
                    break
                dates.append(next_date)
                temp_date = next_date

            # get user's date format safely
            try:
                date_format = self.env['res.lang']._lang_get(self.env.user.lang).date_format
            except Exception:
                date_format = '%Y-%m-%d'

            html = (
                "<div class='alert alert-info' role='alert'>"
                f"<b><i class='fa fa-info-circle mr-1'></i>{_('Upcoming tasks will be created on:')}</b><ul>"
            )
            html += "".join(f"<li>{d.strftime(date_format)}</li>" for d in dates[:5])
            if len(dates) > 5:
                html += "<li>...</li>"
            html += "</ul>"
            if task.repeat_type != 'forever':
                html += f"<small><i>{_('Total scheduled tasks:')} {len(dates)}</i></small>"
            html += "</div>"
            task.recurrence_message = html

    # ---------- Onchange (UI convenience) ----------
    @api.onchange(
        'recurring_task', 'recurrence_start_date', 'repeat_intervals',
        'repeat_unit', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun',
        'repeat_type', 'repeat_number', 'repeat_until'
    )
    def _onchange_recurrence_settings(self):
        if not self.recurring_task:
            self.is_recurring_template = False
            self.next_recurrence_date = False
            return

        self.is_recurring_template = True
        if self.repeat_unit == 'week' and not any([self.mon, self.tue, self.wed, self.thu, self.fri, self.sat, self.sun]):
            today_weekday = fields.Date.today().weekday()
            days_map = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun']
            setattr(self, days_map[today_weekday], True)

        if self._is_recurrence_valid():
            self.next_recurrence_date = self._compute_first_occurrence_date()
        else:
            self.next_recurrence_date = False

        self.recurrence_left = self.repeat_number if self.repeat_type == 'after' else 0

    def _is_recurrence_valid(self):
        self.ensure_one()
        if not self.recurring_task:
            return False
        if self.repeat_unit == 'week' and not any([self.mon, self.tue, self.wed, self.thu, self.fri, self.sat, self.sun]):
            return False
        if (self.repeat_intervals or 0) <= 0:
            return False
        return True

    # ---------- Server-side create/write overrides ----------
    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get('recurring_task') and vals.get('repeat_type', 'forever') in ('forever', 'after'):
                vals['repeat_until'] = False

        records = super(ProjectTask, self).create(vals_list)
        for rec in records.filtered(lambda r: r.recurring_task and r._is_recurrence_valid()):
            try:
                # ensure next_recurrence_date present for server-created templates
                rec.next_recurrence_date = rec._compute_first_occurrence_date()
                if rec.repeat_type == 'after':
                    rec.recurrence_left = rec.repeat_number or 0
                
                # Post message to chatter
                message = rec._get_recurrence_human_readable()
                if message:
                    rec.message_post(body=message)

            except Exception:
                _logger.exception("Error computing first occurrence for new recurring template id=%s", rec.id)
        return records

    def write(self, vals):
        # We need to check the recurrence state before the write
        was_recurring = {rec.id: rec.recurring_task for rec in self}

        # Clear repeat_until if recurrence is not 'until'
        if vals.get('repeat_type') in ('forever', 'after'):
            vals['repeat_until'] = False

        res = super(ProjectTask, self).write(vals)

        keys_affecting_recurrence = {
            'recurring_task', 'recurrence_start_date', 'repeat_intervals', 'repeat_unit',
            'mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun',
            'repeat_type', 'repeat_number', 'repeat_until'
        }
        if keys_affecting_recurrence.intersection(set(vals.keys())):
            for rec in self:
                try:
                    if rec.recurring_task and rec._is_recurrence_valid():
                        # If it just became recurring, post the initial message
                        if not was_recurring.get(rec.id):
                             message = rec._get_recurrence_human_readable()
                             if message:
                                 rec.message_post(body=message)

                        rec.next_recurrence_date = rec._compute_first_occurrence_date()
                        if rec.repeat_type == 'after' and not rec.recurrence_left:
                            rec.recurrence_left = rec.repeat_number or 0
                    else:
                        rec.next_recurrence_date = False
                except Exception:
                    _logger.exception("Error recomputing next_recurrence_date for template id=%s", rec.id)
        return res

    # ---------- Robust cron implementation (idempotent) ----------
    @api.model
    def _cron_create_recurring_tasks(self):
        """
        Idempotent cron:
          1) Compute occurrence_date to process.
          2) Atomically 'claim' the row by advancing next_recurrence_date with a WHERE id=.. AND next_recurrence_date=.. compare.
          3) Only if claim succeeds, create the child with occurrence_date set.
          4) Handle stop conditions.
        """
        today = fields.Date.context_today(self)
        templates = self.sudo().search([
            ('recurring_task', '=', True),
            ('is_recurring_template', '=', True),
            ('next_recurrence_date', '<=', today),
        ])

        _logger.info("CRON: Found %d recurring task templates to process", len(templates))

        for template in templates:
            try:
                _logger.info(
                    "CRON: Processing template id=%s name=%s next=%s",
                    template.id, template.name, template.next_recurrence_date
                )

                # initialize recurrence_left if necessary
                if template.repeat_type == 'after' and (template.recurrence_left in (False, 0)):
                    template.sudo().write({'recurrence_left': template.repeat_number or 0})
                    _logger.info("CRON: Initialized recurrence_left=%s for template %s", template.recurrence_left, template.id)

                occurrence_date = template.next_recurrence_date or template.recurrence_start_date or today
                name_date_str = occurrence_date.strftime("%Y-%m-%d") if hasattr(occurrence_date, "strftime") else str(occurrence_date)

                # Compute next date; if None, stop the template without creating a child
                next_date = template._get_next_occurrence_date(occurrence_date)
                if not next_date:
                    template.sudo().write({'recurring_task': False, 'next_recurrence_date': False})
                    _logger.info("CRON: No next date calculated, stopping template: %s", template.name)
                    continue

                # Atomically claim this occurrence (compare-and-set)
                self.env.cr.execute("""
                    UPDATE project_task
                       SET next_recurrence_date = %s
                     WHERE id = %s
                       AND next_recurrence_date = %s
                    RETURNING id
                """, (next_date, template.id, occurrence_date))
                claimed = bool(self.env.cr.fetchone())
                if not claimed:
                    _logger.info("CRON: Skip template %s (already processed by another worker)", template.id)
                    continue

                # Proceed to create the child only once, after a successful claim
                default_vals = {
                    'name': f"{template.name} - {name_date_str}",
                    'recurring_task': False,
                    'is_recurring_template': False,
                    'parent_id': template.id,
                    'recurring_template_id': template.id,
                    'occurrence_date': occurrence_date,

                    # Do NOT clone subtree or heavy relations on copy
                    'child_ids': [],  # prevent copying subtasks
                }

                # Preserve assignees if present
                if 'user_ids' in template._fields and template.user_ids:
                    default_vals['user_ids'] = [(6, 0, template.user_ids.ids)]
                if 'user_id' in template._fields and template.user_id:
                    default_vals['user_id'] = template.user_id.id

                new_task = None
                try:
                    new_task = template.sudo().copy(default=default_vals)
                    _logger.info("CRON: template.copy succeeded template_id=%s -> new_task_id=%s", template.id, new_task.id)
                except psycopg2.IntegrityError as e:
                    # Unique constraint violation => occurrence already created
                    if getattr(e, 'pgcode', None) == UNIQUE_VIOLATION:
                        self.env.cr.rollback()
                        _logger.info("CRON: Duplicate occurrence guarded by unique constraint for template %s on %s", template.id, occurrence_date)
                        new_task = None
                    else:
                        self.env.cr.rollback()
                        _logger.exception("CRON: IntegrityError creating occurrence for template %s", template.id)
                        raise
                except Exception as e:
                    # Fallback in case the DB adapter exposes pgcode directly
                    if getattr(e, 'pgcode', None) == UNIQUE_VIOLATION:
                        self.env.cr.rollback()
                        _logger.info("CRON: Duplicate occurrence guarded by unique constraint for template %s on %s", template.id, occurrence_date)
                        new_task = None
                    else:
                        _logger.exception("CRON: Unexpected error creating occurrence for template %s", template.id)
                        raise

                if new_task:
                    template.sudo().message_post(
                        body=Markup(f'Recurrent task generated: <span class="o-mail-Message-trackingNew me-1 fw-bold text-info">{new_task.name}</span>'),
                        subtype_xmlid="mail.mt_comment"
                    )
                    _logger.info("CRON: Created new task id=%s name=%s (template id=%s)", new_task.id, new_task.name, template.id)

                # Stopping / further advancement (we already advanced next_recurrence_date on claim)
                if template.repeat_type == 'until' and next_date and template.repeat_until and next_date > template.repeat_until:
                    template.sudo().write({'recurring_task': False, 'next_recurrence_date': False})
                    _logger.info("CRON: Stopped template due to end date: %s", template.name)
                elif template.repeat_type == 'after':
                    new_left = (template.recurrence_left or template.repeat_number or 0) - 1
                    template.sudo().write({'recurrence_left': new_left})
                    _logger.info("CRON: Remaining repetitions for %s: %s", template.name, new_left)
                    if new_left <= 0:
                        template.sudo().write({'recurring_task': False, 'next_recurrence_date': False})
                        _logger.info("CRON: Stopped template after repetitions: %s", template.name)

            except Exception:
                _logger.exception("CRON: Error processing recurring template id=%s", template.id)
                # Let Odoo's transaction handling take care of rollback

        _logger.info("CRON: Finished processing all recurring task templates")

    # ---------- Action helper ----------
    def action_view_generated_tasks(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': f'Tasks Generated from {self.name}',
            'res_model': 'project.task',
            'view_mode': 'tree,form',
            'domain': [('recurring_template_id', '=', self.id)],
            'context': {'create': False}
        }
 