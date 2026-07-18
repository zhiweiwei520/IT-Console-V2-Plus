from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField
from wtforms.validators import DataRequired, Optional


class ManagedTenantForm(FlaskForm):
    entra_tenant_id = StringField("Entra Tenant ID（GUID）", validators=[DataRequired()])
    display_name = StringField("顯示名稱", validators=[DataRequired()])
    domain = StringField("網域（選填，例如 contoso.onmicrosoft.com）", validators=[Optional()])
    client_id = StringField("App Registration Client ID", validators=[DataRequired()])
    client_secret = PasswordField("Client Secret", validators=[DataRequired()])
