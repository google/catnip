Catnip Sandbox
==============

Catnip helps to build a virtual environment to compile and run untrusted programs safely.

With Catnip, you can run untrusted programs in virtual machines protecting the system from possible attacks like:

- exploiting compiler bugs and executing arbitrary code,
- allocating huge memory to make the system crash,
- writing huge files to local filesystems to run out of disk space,
- issuing ``fork(2)`` many times to make the system unstable.

Here are example use cases of Catnip:

- Run continuous integrations in Catnip sandboxes to protect the integration server from crashing accidentally.
- Use Catnip to run and judge submitted programs in public programming contests.


Disclaimer
----------

Catnip is not a Google project, but a personal project maintained by Shuhei Takahashi.
