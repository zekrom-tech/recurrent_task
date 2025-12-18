from odoo import api, fields, models, _

class ProjectTask(models.Model):
    _inherit = "project.task"

    parent_id = fields.Many2one(
        'project.task',
        string="Parent Task",
        readonly=True,  
    )

