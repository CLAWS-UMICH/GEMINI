//########### LTV.json DATA SHAPE ###########//

export interface LtvData {
    location: {
        last_known_x: number
        last_known_y: number
    }
    signal: {
        strength: number
        ping_requested: number
        ping_unlimited_requested: number
    }
}