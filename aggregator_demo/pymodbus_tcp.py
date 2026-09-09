from __future__ import annotations

import time

from pymodbus.client import ModbusTcpClient as LibraryModbusTcpClient
from pymodbus.exceptions import ModbusException

from .modbus_tcp import (
    ALARM_STATE_REGISTER,
    COMMAND_MODE_DISPATCH,
    COMMAND_MODE_SAFE_STATE,
    CONTROLLER_STATE_REGISTER,
    ControllerSnapshot,
    HEARTBEAT_REGISTER,
    MEASURED_SITE_POWER_REGISTER,
    ModbusProtocolError,
    ModbusTransportError,
    POWER_SCALE_KW,
    SITE_EXPORT_SETPOINT_REGISTER,
    SITE_IMPORT_SETPOINT_REGISTER,
    encode_dispatch_request,
    encode_read_request,
    encode_read_response,
    encode_write_response,
    signed_register_value,
)


class PymodbusTcpClient:
    """pymodbus-backed adapter for the existing DepotFlux gateway interface."""

    def __init__(
        self,
        host: str,
        port: int = 1502,
        *,
        timeout_seconds: float = 1.0,
        retries: int = 2,
        retry_delay_seconds: float = 0.05,
        device_id: int = 1,
    ):
        if not 0 <= retries <= 3:
            raise ValueError("retries must be between zero and three")
        self.host = host
        self.port = port
        self.timeout_seconds = timeout_seconds
        self.retries = retries
        self.retry_delay_seconds = retry_delay_seconds
        self.device_id = device_id

    def write_setpoint(
        self, setpoint_kw: float, *, transaction_id: int, safe_state: bool = False
    ) -> tuple[bytes, bytes, int]:
        import_register = round(max(0.0, setpoint_kw) / POWER_SCALE_KW)
        export_register = round(max(0.0, -setpoint_kw) / POWER_SCALE_KW)
        mode = COMMAND_MODE_SAFE_STATE if safe_state else COMMAND_MODE_DISPATCH

        def operation(client: LibraryModbusTcpClient):
            return client.write_registers(
                SITE_IMPORT_SETPOINT_REGISTER,
                [import_register, export_register, mode],
                device_id=self.device_id,
            )

        result, attempts = self._execute(operation)
        actual_transaction_id = int(
            getattr(result, "transaction_id", transaction_id)
        )
        request = encode_dispatch_request(
            setpoint_kw,
            transaction_id=actual_transaction_id,
            unit_id=self.device_id,
            safe_state=safe_state,
        )
        response = encode_write_response(
            transaction_id=actual_transaction_id,
            unit_id=self.device_id,
            start_address=SITE_IMPORT_SETPOINT_REGISTER,
            quantity=3,
        )
        return request, response, attempts

    def read_registers(
        self, start_address: int, quantity: int, *, transaction_id: int
    ) -> tuple[list[int], bytes, bytes, int]:
        def operation(client: LibraryModbusTcpClient):
            return client.read_holding_registers(
                start_address,
                count=quantity,
                device_id=self.device_id,
            )

        result, attempts = self._execute(operation)
        actual_transaction_id = int(
            getattr(result, "transaction_id", transaction_id)
        )
        request = encode_read_request(
            start_address,
            quantity,
            transaction_id=actual_transaction_id,
            unit_id=self.device_id,
        )
        values = [int(value) for value in result.registers]
        if len(values) != quantity:
            raise ModbusProtocolError("pymodbus returned an incomplete register snapshot")
        response = encode_read_response(
            values,
            transaction_id=actual_transaction_id,
            unit_id=self.device_id,
        )
        return values, request, response, attempts

    def snapshot(self, *, transaction_id: int) -> ControllerSnapshot:
        values, _, _, _ = self.read_registers(
            SITE_IMPORT_SETPOINT_REGISTER,
            HEARTBEAT_REGISTER - SITE_IMPORT_SETPOINT_REGISTER + 1,
            transaction_id=transaction_id,
        )
        origin = SITE_IMPORT_SETPOINT_REGISTER
        return ControllerSnapshot(
            import_setpoint_kw=values[0] * POWER_SCALE_KW,
            export_setpoint_kw=values[
                SITE_EXPORT_SETPOINT_REGISTER - origin
            ]
            * POWER_SCALE_KW,
            measured_site_power_kw=signed_register_value(
                values[MEASURED_SITE_POWER_REGISTER - origin]
            ),
            controller_state=values[CONTROLLER_STATE_REGISTER - origin],
            alarm_state=values[ALARM_STATE_REGISTER - origin],
            heartbeat=values[HEARTBEAT_REGISTER - origin],
        )

    def _execute(self, operation):
        last_error: Exception | None = None
        for attempt in range(1, self.retries + 2):
            client = LibraryModbusTcpClient(
                self.host,
                port=self.port,
                timeout=self.timeout_seconds,
            )
            try:
                if not client.connect():
                    raise ModbusTransportError("pymodbus could not connect")
                response = operation(client)
                if response.isError():
                    raise ModbusProtocolError(f"pymodbus exception response: {response}")
                return response, attempt
            except (OSError, ModbusException, ModbusProtocolError, ModbusTransportError) as exc:
                last_error = exc
                if attempt <= self.retries:
                    time.sleep(self.retry_delay_seconds)
            finally:
                client.close()
        raise ModbusTransportError(
            f"pymodbus exchange failed after {self.retries + 1} attempts: {last_error}"
        ) from last_error
