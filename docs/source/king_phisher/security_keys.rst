:mod:`security_keys`
====================

.. module:: security_keys
   :synopsis:

This module provides functionality for working with security keys that are
used for data integrity checks. Verification is performed using ECDSA keys.

Data
----

.. autodata:: king_phisher.security_keys.ecdsa_curves
   :annotation:

Functions
---------

.. autofunction:: king_phisher.security_keys.openssl_decrypt_data

.. autofunction:: king_phisher.security_keys.openssl_derive_key_and_iv

Classes
-------

.. autoclass:: king_phisher.security_keys.SecurityKeys
   :show-inheritance:
   :members:
   :inherited-members:
   :special-members: __init__

.. autoclass:: king_phisher.security_keys.SigningKey
   :show-inheritance:
   :members:

.. autoclass:: king_phisher.security_keys.VerifyingKey
   :show-inheritance:
   :members:
