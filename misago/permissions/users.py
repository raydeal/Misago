from asyncio import gather

from ..context import Context
from ..users.models import User, UserGroup
from .cache import get_permissions_cache, set_permissions_cache
from .groups import get_groups_permissions
from .hooks import get_anonymous_permissions_hook, get_user_permissions_hook
from .permissions import CorePermission
from .queries import moderators_query
from .utils import add_permission


async def get_user_permissions(context: Context, user: User) -> dict:
    return await get_user_permissions_hook.call_action(
        get_user_permissions_action, context, user
    )


async def get_user_permissions_action(context: Context, user: User) -> dict:
    permissions = await get_permissions_cache(context["cache_versions"], user.perms_id)
    if permissions is None:
        permissions = await build_user_permissions(context, user)
        await set_permissions_cache(
            context["cache_versions"], user.perms_id, permissions
        )

    if user.is_moderator:
        add_permission(permissions["core"], CorePermission.MODERATOR)
    if user.is_admin:
        add_permission(permissions["core"], CorePermission.ADMIN)

    return permissions


async def build_user_permissions(context: Context, user: User) -> dict:
    user_groups, moderated_categories = await gather(
        user.get_groups(),
        moderators_query.filter(group_id__in=user.groups_ids).all_flat("category_id"),
    )
    return await get_groups_permissions(
        context, user_groups, moderated_categories=moderated_categories
    )


ANONYMOUS_PERMS_ID = "anon"


async def get_anonymous_permissions(context: Context) -> dict:
    permissions = await get_permissions_cache(
        context["cache_versions"], ANONYMOUS_PERMS_ID
    )
    if permissions is None:
        permissions = await get_anonymous_permissions_hook.call_action(
            get_anonymous_permissions_action, context
        )
        await set_permissions_cache(
            context["cache_versions"], ANONYMOUS_PERMS_ID, permissions
        )

    return permissions


async def get_anonymous_permissions_action(context: Context) -> dict:
    user_groups = await UserGroup.query.filter(is_guest=True).all()
    permissions = await get_groups_permissions(context, user_groups, anonymous=True)

    if CorePermission.MODERATOR in permissions["core"]:
        permissions["core"].remove(CorePermission.MODERATOR)
    if CorePermission.ADMIN in permissions["core"]:
        permissions["core"].remove(CorePermission.ADMIN)

    return permissions
