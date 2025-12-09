"""
Internationalization support using Fluent.

This module provides Fluent-based localization with:
- Multiple language support (ru, en)
- Variable interpolation
- Fallback to default language
- Random response selection for lists
"""
import random
from pathlib import Path
from typing import Any

from fluent_compiler.bundle import FluentBundle


class FluentLocalization:
    """
    Fluent-based localization manager.
    
    Loads .ftl files from locales directory and provides
    translation lookup with variable support.
    """
    
    def __init__(
        self,
        locales_dir: str | Path = "locales",
        default_locale: str = "ru"
    ) -> None:
        """
        Initialize localization.
        
        Args:
            locales_dir: Path to locales directory
            default_locale: Default language code
        """
        self.locales_dir = Path(locales_dir)
        self.default_locale = default_locale
        self.bundles: dict[str, FluentBundle] = {}
        
        self._load_locales()
    
    def _load_locales(self) -> None:
        """Load all locale files from the locales directory."""
        if not self.locales_dir.exists():
            raise FileNotFoundError(f"Locales directory not found: {self.locales_dir}")
        
        for locale_dir in self.locales_dir.iterdir():
            if not locale_dir.is_dir():
                continue
            
            locale_code = locale_dir.name
            ftl_content = ""
            
            # Load all .ftl files in the locale directory
            for ftl_file in locale_dir.glob("*.ftl"):
                ftl_content += ftl_file.read_text(encoding="utf-8") + "\n"
            
            if ftl_content:
                bundle = FluentBundle.from_string(locale_code, ftl_content)
                self.bundles[locale_code] = bundle
        
        if not self.bundles:
            raise ValueError(f"No locales found in {self.locales_dir}")
        
        if self.default_locale not in self.bundles:
            # Fall back to first available locale
            self.default_locale = next(iter(self.bundles.keys()))
    
    def get(
        self,
        key: str,
        locale: str | None = None,
        **kwargs: Any
    ) -> str:
        """
        Get localized string.
        
        Args:
            key: Message ID (e.g., "error-no-reply")
            locale: Language code (uses default if None)
            **kwargs: Variables for interpolation
        
        Returns:
            Localized string, or key if not found
        """
        locale = locale or self.default_locale
        
        # Try requested locale first
        bundle = self.bundles.get(locale)
        if bundle:
            try:
                result = bundle.format(key, kwargs)
                # format() returns (string, errors) tuple
                if result and result[0]:
                    return result[0]
            except KeyError:
                pass  # Key not found in this locale
        
        # Fallback to default locale
        if locale != self.default_locale:
            bundle = self.bundles.get(self.default_locale)
            if bundle:
                try:
                    result = bundle.format(key, kwargs)
                    if result and result[0]:
                        return result[0]
                except KeyError:
                    pass  # Key not found in default locale either
        
        # Return key if not found
        return key
    
    def get_random(
        self,
        key: str,
        locale: str | None = None,
        **kwargs: Any
    ) -> str:
        """
        Get a random localized string from a list value.
        
        The translation should use '---' as delimiter between options.
        Each option can be multiline.
        
        Example .ftl file:
            bu-responses =
                Бугага!
                ---
                Не пугай так!
                ---
                Боже ..
        
        Args:
            key: Key for the list translation
            locale: Language code (uses default if None)
            **kwargs: Variables for interpolation
        
        Returns:
            Random item from the translation
        """
        result = self.get(key, locale, **kwargs)
        
        # If key wasn't found, return as-is
        if result == key:
            return result
        
        # Split by delimiter and filter empty items
        items = [item.strip() for item in result.split("---") if item.strip()]
        
        if not items:
            return key
        
        return random.choice(items)
    
    def __call__(
        self,
        key: str,
        locale: str | None = None,
        **kwargs: Any
    ) -> str:
        """Shortcut for get()."""
        return self.get(key, locale, **kwargs)
    
    @property
    def available_locales(self) -> list[str]:
        """Get list of available locale codes."""
        return list(self.bundles.keys())


# Global instance - initialized lazily
_i18n: FluentLocalization | None = None


def get_i18n() -> FluentLocalization:
    """Get the global i18n instance."""
    global _i18n
    if _i18n is None:
        from config import config
        _i18n = FluentLocalization(
            locales_dir="locales",
            default_locale=config.locale.default
        )
    return _i18n


def _(key: str, locale: str | None = None, **kwargs: Any) -> str:
    """
    Translate a string using the global i18n instance.
    
    This is the main function to use for translations:
    
        from core.i18n import _
        
        message = _("error-no-reply")
        message = _("report-message", date="2024-01-01", chat_id="123", msg_id="456")
    
    Args:
        key: Message ID
        locale: Optional locale override
        **kwargs: Variables for interpolation
    
    Returns:
        Translated string
    """
    return get_i18n().get(key, locale, **kwargs)


def _random(key: str, locale: str | None = None, **kwargs: Any) -> str:
    """
    Get a random translation from a list value.
    
    Use '---' as delimiter between options. Each option can be multiline.
    
    Example .ftl file:
        bu-responses =
            Бугага!
            ---
            Не пугай так!
            ---
            Multiline response
            with second line
    
    Usage:
        from core.i18n import _random
        
        response = _random("bu-responses")
        comment = _random("bot-comments")
    
    Args:
        key: Translation key
        locale: Optional locale override
        **kwargs: Variables for interpolation
    
    Returns:
        Random item from the translation
    """
    return get_i18n().get_random(key, locale, **kwargs)


# Backwards compatibility alias
def get_string(key: str, **kwargs: Any) -> str:
    """
    Legacy function for backwards compatibility.
    
    Converts underscore keys to hyphen format:
        get_string("error_no_reply") -> _("error-no-reply")
    """
    # Convert underscore to hyphen for Fluent format
    fluent_key = key.replace("_", "-")
    return _(fluent_key, **kwargs)
