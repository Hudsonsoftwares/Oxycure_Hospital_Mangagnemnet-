{
    'name': 'NovaCare',
    'version': '18.0.1.0.0',
    'summary': 'NovaCare Hospital Management System',
    'description': """
NovaCare Hospital Management System
===================================
Custom Hospital Management Module
""",
    'author': 'Nimya Thomas',
    'website': '',
    'category': 'Healthcare',
    'license': 'LGPL-3',
    'depends': ['base', 'mail'],
    
    'data': [
        'security/ir.model.access.csv',
        'data/patient_sequence.xml',
        'data/department_sequence.xml',
        'data/doctor_sequence.xml',
        'data/appointment_sequence.xml',
        'data/op_sequence.xml',
        'data/lab_request_sequence.xml',
        'data/billing_sequence.xml',
        'data/pharmacy_sequence.xml',
        'data/billing_email_template.xml',
        'views/patient_views.xml',
        'views/department_views.xml',
        'views/doctor_views.xml',
        'views/appointment_views.xml',
        'views/op_views.xml',
        'views/medicine_views.xml',
        'views/lab_test_views.xml',
        'views/lab_operations_views.xml',
        'views/billing_views.xml',
        'views/billing_report.xml',
        'views/pharmacy_views.xml',
        'views/dashboard_views.xml',
    ],
    'installable': True,
    'application': True,
    'auto_install': False,
}