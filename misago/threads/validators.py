from typing import Any, List, Type, cast

from ..categories.loaders import categories_loader
from ..categories.models import Category, CategoryType
from ..conf.types import Settings
from ..context import Context
from ..validation import BulkValidator, ErrorsList, Validator, sluggablestr
from .errors import (
    PostIsThreadStartError,
    PostNotAuthorError,
    PostNotFoundError,
    ThreadIsClosedError,
    ThreadNotAuthorError,
    ThreadNotFoundError,
)
from .loaders import posts_loader, threads_loader
from .models import Post, Thread


class PostAuthorValidator:
    _context: Context

    def __init__(self, context: Context):
        self._context = context

    async def __call__(self, post: Post, *_) -> Post:
        user = self._context["user"]
        if not user:
            raise PostNotAuthorError(post_id=post.id)
        if not user.is_moderator and user.id != post.poster_id:
            raise PostNotAuthorError(post_id=post.id)
        return post


class PostCategoryValidator:
    _context: Context

    def __init__(self, context: Context, category_validator: Validator):
        self._context = context
        self._validator = category_validator

    @property
    def category_validator(self) -> Validator:
        return self._validator

    async def __call__(self, post: Post, errors: ErrorsList, field_name: str) -> Post:
        category = await categories_loader.load(self._context, post.category_id)
        category = cast(Category, category)
        await self._validator(category, errors, field_name)
        return post


class PostExistsValidator:
    _context: Context
    _category_type: int

    def __init__(self, context: Context, category_type: int = CategoryType.THREADS):
        self._context = context
        self._category_type = category_type

    async def __call__(self, post_id: int, *_) -> Post:
        post = await posts_loader.load(self._context, post_id)
        if not post:
            raise PostNotFoundError(post_id=post_id)
        category_type = await _get_category_type(self._context, post.category_id)
        if category_type != self._category_type:
            raise PostNotFoundError(post_id=post_id)
        return post


async def _get_category_type(context: Context, category_id: int) -> int:
    category = await categories_loader.load(context, category_id)
    if category:
        return category.type
    return 0


class PostThreadValidator:
    _context: Context

    def __init__(self, context: Context, thread_validator: Validator):
        self._context = context
        self._validator = thread_validator

    @property
    def thread_validator(self) -> Validator:
        return self._validator

    async def __call__(self, post: Post, errors: ErrorsList, field_name: str) -> Post:
        thread = await threads_loader.load(self._context, post.thread_id)
        thread = cast(Thread, thread)
        await self._validator(thread, errors, field_name)
        return post


class PostsBulkValidator(BulkValidator):
    async def __call__(
        self, threads: List[Any], errors: ErrorsList, field_name: str
    ) -> List[Post]:
        return await super().__call__(threads, errors, field_name)


class ThreadAuthorValidator:
    _context: Context

    def __init__(self, context: Context):
        self._context = context

    async def __call__(self, thread: Thread, *_) -> Thread:
        user = self._context["user"]
        if not user:
            raise ThreadNotAuthorError(thread_id=thread.id)
        if not user.is_moderator and user.id != thread.starter_id:
            raise ThreadNotAuthorError(thread_id=thread.id)
        return thread


class ThreadCategoryValidator:
    _context: Context

    def __init__(self, context: Context, category_validator: Validator):
        self._context = context
        self._validator = category_validator

    @property
    def category_validator(self) -> Validator:
        return self._validator

    async def __call__(
        self, thread: Thread, errors: ErrorsList, field_name: str
    ) -> Thread:
        category = await categories_loader.load(self._context, thread.category_id)
        category = cast(Category, category)
        await self._validator(category, errors, field_name)
        return thread


class ThreadExistsValidator:
    _context: Context
    _category_type: int

    def __init__(self, context: Context, category_type: int = CategoryType.THREADS):
        self._context = context
        self._category_type = category_type

    async def __call__(self, thread_id: int, *_) -> Thread:
        thread = await threads_loader.load(self._context, thread_id)
        if not thread:
            raise ThreadNotFoundError(thread_id=thread_id)
        category_type = await _get_category_type(self._context, thread.category_id)
        if category_type != self._category_type:
            raise ThreadNotFoundError(thread_id=thread_id)
        return thread


class ThreadIsOpenValidator:
    _context: Context

    def __init__(self, context: Context):
        self._context = context

    async def __call__(self, thread: Thread, *_) -> Thread:
        if thread.is_closed:
            user = self._context["user"]
            if not user or not user.is_moderator:
                raise ThreadIsClosedError(thread_id=thread.id)
        return thread


class ThreadPostExistsValidator:
    _context: Context
    _thread: Thread

    def __init__(self, context: Context, thread: Thread):
        self._context = context
        self._thread = thread

    async def __call__(self, post_id: int, *_) -> Post:
        post = await posts_loader.load(self._context, post_id)
        if not post or post.thread_id != self._thread.id:
            raise PostNotFoundError(post_id=post_id)
        return post


class ThreadPostIsReplyValidator:
    _thread: Thread

    def __init__(self, thread: Thread):
        self._thread = thread

    async def __call__(self, post: Post, *_) -> Post:
        if post and post.id == self._thread.first_post_id:
            raise PostIsThreadStartError(post_id=post.id)
        return post


class ThreadsBulkValidator(BulkValidator):
    async def __call__(
        self, threads: List[Any], errors: ErrorsList, field_name: str
    ) -> List[Thread]:
        return await super().__call__(threads, errors, field_name)


def threadtitlestr(settings: Settings) -> Type[str]:
    return sluggablestr(
        min_length=cast(int, settings["thread_title_min_length"]),
        max_length=cast(int, settings["thread_title_max_length"]),
    )
