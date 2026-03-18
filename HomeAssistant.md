# Home Assistant Integration

## ONVIF

The [Home Assistant ONVIF integration](https://www.home-assistant.io/integrations/onvif/) server is required for PTZ controls, but actually not needed for picture.

## WebRTC for RTSP Live Preview

[AlexxIT/WebRTC](https://github.com/AlexxIT/WebRTC) is required for good RTSP stream live preview on the HA dashboard.

### Dashboard Card Example

```yaml
type: custom:webrtc-camera
url: rtsp://192.168.12.152:8554/mainstream
mode: mse
media: video
ui: true
ptz:
  service: script.camera_ptz_move
  data_left:
    device_id: 9988e31c6b755fdef9bdc6f57c42b799
    direction: LEFT
  data_right:
    device_id: 9988e31c6b755fdef9bdc6f57c42b799
    direction: RIGHT
  data_up:
    device_id: 9988e31c6b755fdef9bdc6f57c42b799
    direction: UP
  data_down:
    device_id: 9988e31c6b755fdef9bdc6f57c42b799
    direction: DOWN
```

### PTZ Move Script

```yaml
alias: Camera PTZ Move
mode: single
fields:
  device_id:
    description: ONVIF camera device ID
    selector:
      device:
        integration: onvif
  direction:
    description: Direction to move the camera
    selector:
      select:
        options:
          - LEFT
          - RIGHT
          - UP
          - DOWN
sequence:
  - variables:
      base:
        move_mode: RelativeMove
        distance: 0.25
        speed: 0.01
        continuous_duration: 0.5
      pan_part: "{{ {'pan': direction} if direction in ['LEFT','RIGHT'] else {} }}"
      tilt_part: "{{ {'tilt': direction} if direction in ['UP','DOWN'] else {} }}"
  - action: onvif.ptz
    target:
      device_id: "{{ device_id }}"
    data: "{{ base | combine(pan_part) | combine(tilt_part) }}"
```
