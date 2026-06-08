FROM cbadenes/r4r:latest@sha256:adb14ef4628b7dde02894c60d78b65a812d410619e872fb464acca1c9d891b93

# Replace the image's bundled example resources with the OpenCitations ones.
RUN rm -rf /resources/*
COPY resources/ /resources/

EXPOSE 7777
