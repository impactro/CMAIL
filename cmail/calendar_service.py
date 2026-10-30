"""Calendar capabilities and confirmed effects, isolated from mail composition."""
from __future__ import annotations

from .principal import READ_MAIL, MANAGE_MAIL, Principal


class CalendarOperations:
    def __init__(self, provider_for, owner_for, store):
        self._provider, self._owner, self.store = provider_for, owner_for, store

    def calendars(self, principal: Principal) -> list[dict[str, object]]:
        principal.require(READ_MAIL)
        selected = self._provider(principal)
        if not hasattr(selected, "calendars"):
            raise NotImplementedError("O provedor atual não oferece calendário.")
        return selected.calendars()  # type: ignore[attr-defined]

    def calendar_view(self, principal: Principal, start: str, end: str, time_zone: str, *, calendar_id: str = "", limit: int = 100) -> list[dict[str, object]]:
        principal.require(READ_MAIL)
        selected = self._provider(principal)
        if not hasattr(selected, "calendar_view"):
            raise NotImplementedError("O provedor atual não oferece calendário.")
        return selected.calendar_view(start, end, time_zone, calendar_id, limit)  # type: ignore[attr-defined]

    def availability(
        self,
        principal: Principal,
        schedules: list[str],
        start: str,
        end: str,
        time_zone: str,
        interval_minutes: int = 30,
    ) -> dict[str, object]:
        principal.require(READ_MAIL)
        selected = self._provider(principal)
        if not hasattr(selected, "availability"):
            raise NotImplementedError("O provedor atual não oferece disponibilidade.")
        return selected.availability(  # type: ignore[attr-defined]
            schedules, start, end, time_zone, interval_minutes,
        )

    def event(self, principal: Principal, identifier: str) -> dict[str, object]:
        principal.require(READ_MAIL)
        selected = self._provider(principal)
        if not hasattr(selected, "event"):
            raise NotImplementedError("O provedor atual não oferece calendário.")
        return selected.event(identifier)  # type: ignore[attr-defined]

    def create_event(self, principal: Principal, event: dict[str, object], *, calendar_id: str = "", confirmed: bool = False) -> dict[str, object]:
        principal.require(MANAGE_MAIL)
        if not confirmed:
            raise ValueError("A criação do evento exige confirmação explícita.")
        selected = self._provider(principal)
        if not hasattr(selected, "create_event"):
            raise NotImplementedError("O provedor atual não oferece calendário.")
        result = selected.create_event(event, calendar_id=calendar_id)  # type: ignore[attr-defined]
        self.store.record_action(
            "calendar-create", "completed",
            {"calendarId": str(calendar_id)[:1024]}, self._owner(principal),
        )
        return result

    def update_event(self, principal: Principal, identifier: str, changes: dict[str, object], *, confirmed: bool = False) -> dict[str, object]:
        principal.require(MANAGE_MAIL)
        if not confirmed:
            raise ValueError("A alteração do evento exige confirmação explícita.")
        selected = self._provider(principal)
        if not hasattr(selected, "update_event"):
            raise NotImplementedError("O provedor atual não oferece calendário.")
        result = selected.update_event(identifier, changes)  # type: ignore[attr-defined]
        self.store.record_action(
            "calendar-update", "completed",
            {"eventId": str(identifier)[:1024], "fields": sorted(str(key) for key in changes)},
            self._owner(principal),
        )
        return result

    def delete_event(self, principal: Principal, identifier: str, *, confirmed: bool = False) -> dict[str, object]:
        principal.require(MANAGE_MAIL)
        if not confirmed:
            raise ValueError("A remoção do evento exige confirmação explícita.")
        selected = self._provider(principal)
        if not hasattr(selected, "delete_event"):
            raise NotImplementedError("O provedor atual não oferece calendário.")
        result = selected.delete_event(identifier)  # type: ignore[attr-defined]
        self.store.record_action(
            "calendar-delete", "completed",
            {"eventId": str(identifier)[:1024]}, self._owner(principal),
        )
        return result

    def respond_event(self, principal: Principal, identifier: str, response: str, *, comment: str = "", send_response: bool = True, confirmed: bool = False) -> dict[str, object]:
        principal.require(MANAGE_MAIL)
        if not confirmed:
            raise ValueError("A resposta ao evento exige confirmação explícita.")
        selected = self._provider(principal)
        if not hasattr(selected, "respond_event"):
            raise NotImplementedError("O provedor atual não oferece calendário.")
        result = selected.respond_event(identifier, response, comment, send_response)  # type: ignore[attr-defined]
        self.store.record_action(
            "calendar-respond", "completed",
            {"eventId": str(identifier)[:1024], "response": str(response)[:32]},
            self._owner(principal),
        )
        return result
