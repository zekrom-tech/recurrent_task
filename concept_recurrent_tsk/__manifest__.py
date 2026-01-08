# -*- coding: utf-8 -*-
{
    'name': 'Project Recurring Tasks | Auto Task Generator | Task Scheduler',
    'version': '17.0.1.0.0',
    'summary': 'Automate recurring tasks in projects with flexible scheduling - Daily, Weekly, Monthly, Yearly task automation',
    'description': """
Project Recurring Tasks - Automate Your Task Management
========================================================

🔄 **Automate Repetitive Tasks with Ease**

This powerful module enables automatic generation of recurring tasks in your Odoo Projects. 
Save time and never miss a deadline by automating repetitive task creation.

Key Features
------------
✅ **Flexible Recurrence Patterns**
   - Daily, Weekly, Monthly, and Yearly scheduling
   - Custom interval support (every X days/weeks/months)
   - Set specific days of the week

✅ **Smart Task Generation**
   - Automatic task creation based on schedule
   - Inherits all task properties (assignee, tags, priority)
   - Maintains task relationships and dependencies

✅ **Visual Indicators**
   - Clear recurring task badges in list views
   - Easy identification of parent/child recurring tasks
   - Dedicated recurrence information panel

✅ **Full Control**
   - Start and end dates for recurrence
   - Pause and resume recurring tasks
   - Edit individual occurrences without affecting series

Perfect For
-----------
📋 Regular maintenance tasks
📋 Weekly team meetings
📋 Monthly reporting
📋 Periodic reviews and audits
📋 Scheduled client follow-ups

Technical Information
---------------------
- Compatible with Odoo 17.0
- Integrates seamlessly with Project module
- Cron-based automatic task generation
- Lightweight and performance optimized

Support
-------
For support, customization, or feature requests, contact us at info@csloman.com
    """,
    'category': 'Project/Project',
    'author': 'Concept Solutions LLC',
    'website': 'https://www.csloman.com/',
    'support': 'info@csloman.com',
    'license': 'LGPL-3',
    'images': ['static/description/image.png'],
    'depends': [
        'project',
    ],
    'data': [
        'security/ir.model.access.csv',
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
    'application': True,
    'auto_install': False,
}
