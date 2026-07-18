from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import BooleanField, PasswordField, SelectField, StringField
from wtforms.validators import DataRequired, Optional


class PrincipalForm(FlaskForm):
    display_name = StringField("顯示名稱", validators=[DataRequired()])
    platform_username = StringField("平台帳號（選填）", validators=[Optional()])
    platform_password = PasswordField("密碼（設定帳號時必填）", validators=[Optional()])
    platform_operator = BooleanField("授予平台管理者權限（platform_operator）")


class EnvironmentForm(FlaskForm):
    slug = StringField("環境代碼（slug）", validators=[DataRequired()])
    name = StringField("環境名稱", validators=[DataRequired()])


class MembershipForm(FlaskForm):
    principal_id = SelectField("使用者", validators=[DataRequired()])
    role_code = SelectField("角色", validators=[DataRequired()])
    all_managed_tenants = BooleanField("授予此環境全部 Managed Tenant")
