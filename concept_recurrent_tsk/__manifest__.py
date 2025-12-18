# -*- coding: utf-8 -*-
{
    'name': 'Project Recurring Tasks',
    'version': '17.0.1.0',
    'summary': 'Adds support for recurring tasks in projects.',
    'description': """
        This module allows users to define recurring tasks that are
        automatically generated based on a schedule.
    """,
    'category': 'Project',
    'author': 'Your Name',
    'license': 'Other proprietary',
    'depends': [
        'project', # Important dependency
    ],
    'data': [
        'security/ir.model.access.csv', # Remember to add access rights
        'views/project_task_view.xml',
        'views/magic_hider.xml',
        'views/tree_view.xml',
        'views/extra_info.xml',
        'data/cron_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'concept_recurrent_tsk/static/src/scss/recur_indicator.scss',
        ],
    },
    'installable': True,
    'application': False,
    'auto_install': False,
}
