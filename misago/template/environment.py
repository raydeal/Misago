from typing import List

from jinja2 import ChoiceLoader, Environment, PackageLoader, select_autoescape

from ..conf import settings
from ..plugins import plugins_loader
from ..translations import translations
from .hooks import jinja2_extensions_hook, jinja2_filters_hook


def get_template_loaders() -> List[PackageLoader]:
    template_loaders = [PackageLoader("misago.template", "templates")]
    for plugin, _ in plugins_loader.get_plugins_with_directory("templates"):
        template_loaders.append(PackageLoader(plugin.package_name, "templates"))
    return list(reversed(template_loaders))


def get_jinja2_environment() -> Environment:
    env = Environment(
        auto_reload=settings.debug,
        autoescape=select_autoescape(["html", "svg", "xml"]),
        enable_async=True,
        extensions=["jinja2.ext.i18n"],
        loader=ChoiceLoader(get_template_loaders()),
    )

    env.install_gettext_translations(translations.load("en"))  # type: ignore

    env.filters.update(jinja2_filters_hook)
    for extension in jinja2_extensions_hook:
        env.add_extension(extension)

    return env


env = get_jinja2_environment()
