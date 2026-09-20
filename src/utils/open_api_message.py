#!/usr/bin/env python3
"""
This module defines the base class `OpenAPIMessage`.

The `OpenAPIMessage` class serves as an abstract base class for messages
in an OpenAPI-based system. It provides method stubs that subclasses
must implement to define message behavior.
"""
from abc import ABC, abstractmethod


class OpenAPIMessage(ABC):
    """
    Abstract base class for OpenAPI messages.
    """

    @abstractmethod
    def payload_type(self):
        """
        Returns the type of the payload.

        This method must be implemented by subclasses.
        """
        pass

    @abstractmethod
    def payload(self):
        """
        Returns the actual payload of the message.

        This method must be implemented by subclasses.
        """
        pass

    @abstractmethod
    def client_msg_id(self):
        """
        Returns the client message ID.

        This method must be implemented by subclasses.
        """
        pass

    @abstractmethod
    def as_json_string(self):
        """
        Returns the message as a JSON string.

        This method must be implemented by subclasses.
        """
        pass
