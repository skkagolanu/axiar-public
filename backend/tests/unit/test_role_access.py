"""Tests for role-based access control fixes"""

from unittest.mock import Mock

import pytest

from app.api.dependencies.auth import require_role
from app.core.exceptions import AuthorizationError
from app.domain.user.models import User, UserRole


class TestRequireRole:
    """Test require_role dependency with various input types"""

    def test_require_role_with_string(self):
        """Test require_role accepts string role"""
        user = Mock(spec=User)
        user.role = UserRole.ADMIN

        dependency = require_role("admin")
        result = dependency(current_user=user)

        assert result == user

    def test_require_role_with_enum(self):
        """Test require_role accepts enum role"""
        user = Mock(spec=User)
        user.role = UserRole.ADMIN

        dependency = require_role(UserRole.ADMIN)
        result = dependency(current_user=user)

        assert result == user

    def test_require_role_with_list_of_enums(self):
        """Test require_role accepts list of enum roles"""
        user = Mock(spec=User)
        user.role = UserRole.FIELD_AGENT

        dependency = require_role([UserRole.FIELD_AGENT, UserRole.ADMIN])
        result = dependency(current_user=user)

        assert result == user

    def test_require_role_with_list_of_strings(self):
        """Test require_role accepts list of string roles"""
        user = Mock(spec=User)
        user.role = UserRole.PROVIDER

        dependency = require_role(["provider", "admin"])
        result = dependency(current_user=user)

        assert result == user

    def test_require_role_fails_wrong_role(self):
        """Test require_role raises error for wrong role"""
        user = Mock(spec=User)
        user.role = UserRole.CUSTOMER

        dependency = require_role("admin")

        with pytest.raises(AuthorizationError):
            dependency(current_user=user)

    def test_require_role_fails_not_in_list(self):
        """Test require_role raises error when role not in list"""
        user = Mock(spec=User)
        user.role = UserRole.CUSTOMER

        dependency = require_role([UserRole.ADMIN, UserRole.PROVIDER])

        with pytest.raises(AuthorizationError):
            dependency(current_user=user)
