ARG BUILD_FROM
FROM $BUILD_FROM

RUN \
	apk add --no-cache \
		python3

WORKDIR /data

ENV LANG C.UTF-8

COPY run.sh ./
RUN chmod a+x ./run.sh

CMD [ "./run.sh" ]
