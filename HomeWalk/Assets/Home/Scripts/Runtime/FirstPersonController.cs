using UnityEngine;
using UnityEngine.InputSystem;

namespace HomeWalk
{
    /// Simple house-walking first-person controller (WASD, mouse look, Shift sprint, Space jump).
    [RequireComponent(typeof(CharacterController))]
    public class FirstPersonController : MonoBehaviour
    {
        public Transform cameraPivot;
        public float walkSpeed = 2.6f;
        public float sprintSpeed = 5.5f;
        public float lookSensitivity = 0.12f;
        public float gravity = -20f;
        public float jumpHeight = 1.0f;
        public bool fly;            // F: free flight (no gravity), Space up, Ctrl down
        public bool inputEnabled = true;

        CharacterController _cc;
        float _pitch, _vy;

        void Awake() { _cc = GetComponent<CharacterController>(); }

        void OnEnable()
        {
#if !UNITY_WEBGL || UNITY_EDITOR
            // Browsers only allow pointer lock from a user click, so on WebGL we wait for the first click.
            Cursor.lockState = CursorLockMode.Locked;
            Cursor.visible = false;
#endif
            _pitch = 0f; _vy = 0f;
        }

        void Update()
        {
            var kb = Keyboard.current; var mouse = Mouse.current;
            if (kb == null || !inputEnabled) return;

            if (mouse != null && Cursor.lockState == CursorLockMode.Locked)
            {
                var d = mouse.delta.ReadValue() * lookSensitivity;
                transform.Rotate(0f, d.x, 0f);
                _pitch = Mathf.Clamp(_pitch - d.y, -85f, 85f);
                if (cameraPivot) cameraPivot.localEulerAngles = new Vector3(_pitch, 0f, 0f);
            }
            if (kb.escapeKey.wasPressedThisFrame) { Cursor.lockState = CursorLockMode.None; Cursor.visible = true; }
            if (mouse != null && mouse.leftButton.wasPressedThisFrame) { Cursor.lockState = CursorLockMode.Locked; Cursor.visible = false; }

            var input = new Vector2((kb.dKey.isPressed ? 1 : 0) - (kb.aKey.isPressed ? 1 : 0),
                                    (kb.wKey.isPressed ? 1 : 0) - (kb.sKey.isPressed ? 1 : 0));
            input = Vector2.ClampMagnitude(input, 1f);
            float speed = kb.leftShiftKey.isPressed ? sprintSpeed : walkSpeed;
            var move = (transform.right * input.x + transform.forward * input.y) * speed;
            if (fly)
            {
                var fwd = cameraPivot ? cameraPivot.forward : transform.forward;
                move = (transform.right * input.x + fwd * input.y) * speed * 2f;
                if (kb.spaceKey.isPressed) move.y += speed * 1.5f;
                if (kb.leftCtrlKey.isPressed || kb.cKey.isPressed) move.y -= speed * 1.5f;
                _vy = 0f;
                _cc.Move(move * Time.deltaTime);
                return;
            }

            if (_cc.isGrounded)
            {
                _vy = -2f;
                if (kb.spaceKey.wasPressedThisFrame) _vy = Mathf.Sqrt(jumpHeight * -2f * gravity);
            }
            _vy += gravity * Time.deltaTime;
            move.y = _vy;
            _cc.Move(move * Time.deltaTime);
        }

        public void Teleport(Vector3 pos, float yaw, float pitch = 0f)
        {
            if (_cc == null) _cc = GetComponent<CharacterController>();
            _cc.enabled = false;
            transform.SetPositionAndRotation(pos, Quaternion.Euler(0f, yaw, 0f));
            _pitch = pitch; _vy = 0f;
            if (cameraPivot) cameraPivot.localEulerAngles = new Vector3(_pitch, 0f, 0f);
            _cc.enabled = true;
        }
    }
}
