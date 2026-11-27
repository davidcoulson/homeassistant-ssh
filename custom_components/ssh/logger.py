"""Keep dependency command and sensor payloads out of integration logs."""

import logging


class PayloadFreeLogger(logging.LoggerAdapter):
    """Preserve event levels without forwarding unstructured payloads."""

    def log(self, level, msg, *args, **kwargs):
        # The pinned manager embeds commands, outputs and values in messages.
        # Exception text may include these too; never forward it or its args.
        self.logger.log(level, "SSH manager event (payload omitted)")
