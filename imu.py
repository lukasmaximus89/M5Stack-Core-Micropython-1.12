from lib import mpu6050
import i2c_bus

SH200Q_ADDR = 0x6c
MPU6050_ADDR = 0x68
imu_i2c = i2c_bus.get(i2c_bus.M_BUS)

IMU = mpu6050.MPU6050

if imu_i2c.is_ready(MPU6050_ADDR) or imu_i2c.is_ready(MPU6050_ADDR):
    IMU = mpu6050.MPU6050
