import WidgetKit
import SwiftUI

@main
struct JARVISWidgetBundle: WidgetBundle {
    var body: some Widget {
        JARVISStatusWidget()
        JARVISCalendarWidget()
    }
}
