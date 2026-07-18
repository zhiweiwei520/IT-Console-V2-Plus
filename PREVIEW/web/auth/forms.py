from __future__ import annotations

from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField
from wtforms.validators import DataRequired, Optional


class LoginForm(FlaskForm):
    environment_slug = StringField("環境代碼（留空 = 平台 break-glass 登入）", validators=[Optional()])
    username = StringField("帳號", validators=[DataRequired()])
    password = PasswordField("密碼", validators=[DataRequired()])
