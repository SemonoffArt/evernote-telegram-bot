import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

import settings
from ext.evernote.client import NoteContent, Types, ErrorTypes, EvernoteSdk


class EvernoteApiError(Exception):
    def __init__(self, description=''):
        super(EvernoteApiError, self).__init__(description)


class NoteNotFound(EvernoteApiError):
    pass


class RateLimitReached(EvernoteApiError):
    pass


class AsyncEvernoteApi:

    def __init__(self, loop=None):
        self.loop = loop or asyncio.get_event_loop()
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.sandbox = settings.DEBUG
        self.logger = logging.getLogger('evernote_api')

    def __call_store_method(self, method_name, auth_token, *args, **kwargs):
        try:
            self.logger.debug("Start call '{0}' with args: {1}, kwargs: {2}".format(method_name, args, kwargs))
            sdk = EvernoteSdk(token=auth_token, sandbox=self.sandbox)
            note_store = sdk.get_note_store()
            method = getattr(note_store, method_name)
            result = method(*args, **kwargs)
            self.logger.debug("Finish call '{0}'".format(method_name))
            return result
        except ErrorTypes.EDAMNotFoundException:
            raise NoteNotFound() from None
        except ErrorTypes.EDAMSystemException as e:
            if e.errorCode == 19 and hasattr(e, 'rateLimitDuration'):
                self.logger.error('rateLimitDuration == {0}'.format(e.rateLimitDuration))
                raise RateLimitReached('rateLimitDuration == {0}'.format(e.rateLimitDuration)) from None
            else:
                raise EvernoteApiError("{0}: {1}".format(getattr(e, 'errorCode', ''), getattr(e, 'message', ''))) from None
        except Exception:
            raise EvernoteApiError() from None

    async def get_note(self, auth_token, note_guid):
        def fetch(note_guid):
            return self.__call_store_method('getNote', auth_token, note_guid, True, True, False, False)

        result = await self.loop.run_in_executor(self.executor, fetch, note_guid)
        self.logger.debug('Note fetched.')
        return result

    async def save_note(self, auth_token, note):
        def save(note):
            return self.__call_store_method('createNote', auth_token, note)

        result = await self.loop.run_in_executor(self.executor, save, note)
        self.logger.debug('Note saved.')
        return result

    async def new_note(self, auth_token, notebook_guid, text,
                       title=None, files=None):
        def create():
            note = Types.Note()
            note.title = title or ('%s...' % text[:25] if len(text) > 30 else text)
            note.notebookGuid = notebook_guid
            content = NoteContent(note)
            content.add_text(text)
            if files:
                for path, mime_type in files:
                    content.add_file(path, mime_type)
            note.resources = content.get_resources()
            note.content = str(content)
            return self.__call_store_method('createNote', auth_token, note)

        result = await self.loop.run_in_executor(self.executor, create)
        self.logger.debug('Note created.')
        return result

    async def update_note(self, auth_token, note):
        def update(note):
            return self.__call_store_method('updateNote', auth_token, note)

        result = await self.loop.run_in_executor(self.executor, update, note)
        self.logger.debug('Note updated.')
        return result

    async def get_default_notebook(self, auth_token):
        def get_nb():
            return self.__call_store_method('getDefaultNotebook', auth_token)

        return await self.loop.run_in_executor(self.executor, get_nb)
