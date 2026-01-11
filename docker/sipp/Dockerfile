FROM alpine:3.19

# Install SIPp
RUN apk add --no-cache \
    sipp \
    bash

# Create scenario directory
RUN mkdir -p /scenarios

# Copy SIPp scenarios
COPY scenarios/*.xml /scenarios/

WORKDIR /scenarios

# Default command: run as UAS (server)
CMD ["sipp", "-sn", "uas", "-p", "5060"]
