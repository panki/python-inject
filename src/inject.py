"""
Python dependency injection framework.
"""
import logging
import threading

logger = logging.getLogger('inject')

_INJECTOR = None                    # Shared injector instance.
_INJECTOR_LOCK = threading.RLock()  # Guards injector initialization. 
_BINDING_LOCK = threading.RLock()   # Guards runtime bindings.


def configure(config=None):
    """Create an injector with a callable config or raise an exception when already configured."""
    global _INJECTOR

    with _INJECTOR_LOCK:
        if _INJECTOR:
            raise InjectorException('Injector is already configured')

        _INJECTOR = Injector(config)
        logging.debug('Created and configured an injector, config=%s', config)
        return _INJECTOR


def clear_and_configure(config=None):
    """Clear an existing injector and create another one with a callable config."""
    with _INJECTOR_LOCK:
        clear()
        return configure(config)


def clear():
    """Clear an existing injector if present."""
    global _INJECTOR

    with _INJECTOR_LOCK:
        if _INJECTOR is None:
            return

        _INJECTOR = None
        logging.debug('Cleared an injector')


def instance(cls):
    """Inject an instance of a class."""
    return get_injector_or_die().get_instance(cls)


def attr(cls):
    """Return a attribute injection (descriptor).

    Usage::
        class MyClass(object):
            cache = inject.attr(Cache)

            @classmethod
            def load(cls, id):
                return cls.cache.load('user', id)

            def save(self):
                self.cache.save(self)
    """
    return _AttributeInjection(cls)


def get_injector():
    """Return the current injector or None."""
    return _INJECTOR


def get_injector_or_die():
    """Return the current injector or raise an InjectorException."""
    injector = _INJECTOR
    if not injector:
        raise InjectorException('No injector is configured')

    return injector


class Binder(object):
    def __init__(self):
        self._bindings = {}

    def install(self, config):
        """Install another callable configuration."""
        config(self)
        return self

    def bind(self, cls, instance):
        """Bind a class to an instance."""
        self._check_class(cls)
        self._bindings[cls] = lambda: instance
        logging.debug('Bound %s to a instance %s', cls, instance)
        return self

    def bind_to_constructor(self, cls, constructor):
        """Bind a class to a callable singleton constructor."""
        self._check_class(cls)
        if constructor is None:
            raise InjectorException('Constructor cannot be none for %s', cls)

        self._bindings[cls] = _ConstructorBinding(constructor)
        logging.debug('Bound %s to a constructor %s', cls, constructor)
        return self

    def bind_to_provider(self, cls, provider):
        """Bind a class to a callable instance provider executed for each injection."""
        self._check_class(cls)
        if provider is None:
            raise InjectorException('Provider cannot be none for %s', cls)

        self._bindings[cls] = provider
        logging.debug('Bound %s to a provider %s', cls, provider)
        return self

    def _check_class(self, cls):
        if cls is None:
            raise InjectorException('Binding class cannot be none')

        if cls in self._bindings:
            raise InjectorException('Duplicate binding for %s', cls)


class Injector(object):
    def __init__(self, config=None):
        if config:
            binder = Binder()
            config(binder)
            self._bindings = dict(binder._bindings)
        else:
            self._bindings = {}

    def get_instance(self, cls):
        """Return an instance for a class."""
        binding = self._bindings.get(cls)
        if binding:
            return binding()

        # Try to create a runtime binding.
        with _BINDING_LOCK:
            binding = self._bindings.get(cls)
            if binding:
                return binding()

            if not callable(cls):
                raise InjectorException(
                    'Cannot create a runtime binding for %s, it\'s not callable', cls)

            instance = cls()
            self._bindings[cls] = lambda: instance

            logging.debug('Created a runtime binding for %s, instance %s', cls, instance)
            return instance


class InjectorException(Exception):
    pass


class _ConstructorBinding(object):
    def __init__(self, constructor):
        self._constructor = constructor
        self._created = False
        self._instance = None

    def __call__(self):
        if self._created:
            return self._instance

        with _BINDING_LOCK:
            if self._created:
                return self._instance

            self._created = True
            self._instance = self._constructor()

        return self._instance


class _AttributeInjection(object):
    def __init__(self, cls):
        self._cls = cls

    def __get__(self, obj, owner):
        return instance(self._cls)